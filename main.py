import rumps
import pyaudio
import wave
import threading
import pyperclip
from collections import deque
from openai import OpenAI
import os
import struct
import tempfile
import json
import keyboard
from pydub import AudioSegment

rumps.debug_mode(True)

USE_KEYBOARD = True

if not USE_KEYBOARD:
    keyboard = None

class AudioTranscriberApp(rumps.App):
    def __init__(self):
        super(AudioTranscriberApp, self).__init__("M")
        self.is_recording = False
        self.audio_buffer = deque(maxlen=int(44100 * 60 * 5))
        self.stream = None
        self.p = pyaudio.PyAudio()
        self.input_device_index = self.choose_input_device()
        
        # Flag to choose between OpenAI and AssemblyAI # TODO: Actually make both work
        #  Note: Assembly is better for multichannel; OpenAI is faster.
        self.use_openai = True  # Set to False to use AssemblyAI
        
        # Set up OpenAI client
        self.setup_openai_client()
        
        # Add menu items
        self.menu = ["Start Recording", "Stop Recording", "Transcribe Last 30s", "Choose Input Device"]
        
    def setup_openai_client(self):
        openai_api_key = self.get_openai_api_key()
        if openai_api_key:
            self.client = OpenAI(api_key=openai_api_key)
        else:
            print("Failed to set up OpenAI client. Transcription will not work.")
            self.client = None


    def setup_assemblyai_client(self):
        assemblyai_api_key = self.get_assemblyai_api_key()
        if assemblyai_api_key:
            aai.settings.api_key = assemblyai_api_key
            self.transcriber = aai.Transcriber()
        else:
            print("Failed to set up AssemblyAI client. Transcription will not work.")
            self.transcriber = None

    @staticmethod
    def get_openai_api_key():
        openai_config_path = os.path.expanduser('~/.openai')
        try:
            with open(openai_config_path, 'r') as config_file:
                return config_file.read().strip()
        except FileNotFoundError:
            print("Error: OpenAI config file not found. Please create ~/.openai with your API key.")
        except Exception as e:
            print(f"Error reading ~/.openai file: {str(e)}")
        return None

    @staticmethod
    def get_assemblyai_api_key():
        assemblyai_config_path = os.path.expanduser('~/.assemblyai')
        try:
            with open(assemblyai_config_path, 'r') as config_file:
                return config_file.read().strip()
        except FileNotFoundError:
            print("Error: AssemblyAI config file not found. Please create ~/.assemblyai with your API key.")
        except Exception as e:
            print(f"Error reading ~/.assemblyai file: {str(e)}")
        return None

    @rumps.clicked("Start Recording")
    def start_recording(self):
        if not self.is_recording:
            self.is_recording = True
            threading.Thread(target=self.record, daemon=True).start()
            print("Recording started")
            
    @rumps.clicked("Stop Recording")
    def stop_recording(self, _):
        if self.is_recording:
            self.is_recording = False
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            print("Recording stopped")

    @rumps.clicked("Transcribe Last 30s")
    def transcribe_audio(self, _):
        if not self.client:
            print("OpenAI client not set up. Cannot transcribe.")
            return

        transcription = self.get_last_30s_transcript()
        if transcription:
            pyperclip.copy(transcription)
            print("Transcription complete. Text copied to clipboard.")
        else:
            print("Transcription failed.")

    def get_last_30s_transcript(self):
        if not self.client:
            print("OpenAI client not set up. Cannot transcribe.")
            return None

        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
            temp_filename = temp_audio.name

            # Convert the last 30 seconds of audio to an MP3 file
            audio = AudioSegment(
                data=struct.pack(f"{len(self.audio_buffer)}h", *self.audio_buffer),
                sample_width=2,
                frame_rate=44100,
                channels=1
            )
            audio.export(temp_filename, format="mp3", bitrate="64k")

            try:
                with open(temp_filename, "rb") as audio_file:
                    transcription = self.client.audio.transcriptions.create(
                        model="whisper-1", 
                        file=audio_file, 
                        response_format="text"
                    )
                return transcription
            except Exception as e:
                print(f"Transcription Error: {str(e)}")
                return None
            finally:
                # Remove the temporary file
                os.unlink(temp_filename)

    def record(self):
        try:
            self.stream = self.p.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=44100,
                                      input=True,
                                      input_device_index=self.input_device_index,
                                      frames_per_buffer=1024)
            
            while self.is_recording:
                data = self.stream.read(1024)
                # Convert bytes to integers and extend the buffer
                self.audio_buffer.extend(struct.unpack(f"{len(data)//2}h", data))
                
        except Exception as e:
            print(f"Error in recording: {str(e)}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            self.is_recording = False
    
    def rewrite_text_with_gpt4o(self, notes: str, transcript: str):
        """Rewrite the notes from clipboard with the last 30 seconds of the meeting audio recording."""
        if not self.client:
            print("OpenAI client not set up. Cannot rewrite text.")
            return
        
        messages = [
            {"role": "system", "content": "You are an autocomplete copilot. You are provided with work-in-progress notes that a user is writing while they're in a meeting. You are also given the recent transcript from their microphone. Continue their notes, following the format and text in the existing notes, if relevant. Your notes will be automatically inserted exactly at the end of the notes so far.\n\nDo try to be concise. You do not have to write about everything in the transcript, just what's relevant to autocomplete the notes.\nDo not include any information that does not come from the transcript.\n\n Your response should contain a continuation of the notes as raw text or markdown. Do not include any other text in your response."},
            {"role": "user", "content": f"Transcript:\n\n{transcript}\n\n-----\n\nNotes so far:\n\n{notes}\n\n-----\n\nContinuation:"}
        ]
        print(messages)
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096,
                temperature=0.7,
                stream=True
            )
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta is not None:
                    yield delta
                else:
                    return
        except Exception as e:
            print(f"Error in rewriting text: {str(e)}")
            return
        
    @rumps.clicked("Rewrite Notes (⌘⇧P)")
    def rewrite_notes(self, _=None):
        print("Rewrite Notes (⌘⇧P) clicked")
        canceled = False
        remove_hotkey = lambda: None

        def cancel():
            nonlocal canceled, remove_hotkey
            canceled = True
        
        callback = keyboard.add_hotkey('esc', cancel)
        remove_hotkey = lambda:keyboard.remove_hotkey(callback)

        if not self.client:
            print("OpenAI client not set up. Cannot rewrite text.")
            return


        # notes = pyperclip.paste()
        transcript = self.get_last_30s_transcript()
        
        # Empty the audio buffer
        self.audio_buffer.clear()

        if canceled:
            return
        pyperclip.copy(transcript)

        keyboard.press('command+v')
        keyboard.release('command+v')
        # completed_notes = ""
        # for chunk in self.rewrite_text_with_gpt4o(notes, transcript):
        #     if canceled:
        #         return
        #     completed_notes += chunk
        #     keyboard.write(chunk)
        
        remove_hotkey()

        # if completed_notes:
        #     pyperclip.copy(completed_notes)
        #     print("Notes rewritten and copied to clipboard.")
        #     # Notify the user
        #     rumps.notification("Notes Rewritten", "Notes have been rewritten and copied to clipboard.", "Note", sound=False)
        # else:
        #     print("Failed to rewrite notes.")
        #     # Notify the user
        #     rumps.notification("Notes Rewritten", "Failed to rewrite notes.", "Note")

    def choose_input_device(self):
        devices = []
        for i in range(self.p.get_device_count()):
            device_info = self.p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:  # This is an input device
                devices.append((i, device_info['name']))
        
        if any(device[1].lower().startswith("aggregate") for device in devices):
            i = devices.index(next((device for device in devices if device[1].lower().startswith("aggregate")), None))
            return devices[i][0]
            

        print("Available input devices:")
        for i, (index, name) in enumerate(devices):
            print(f"{i + 1}. {name}")
        
        choice = input("Choose the input device (enter the number): ")
        try:
            choice = int(choice) - 1
            if 0 <= choice < len(devices):
                return devices[choice][0]
            else:
                print("Invalid choice. Using default input device.")
                return None
        except ValueError:
            print("Invalid input. Using default input device.")
            return None

    @rumps.clicked("Choose Input Device")
    def change_input_device(self, _):
        new_device_index = self.choose_input_device()
        if new_device_index is not None:
            self.input_device_index = new_device_index
            print(f"Input device changed to: {self.p.get_device_info_by_index(self.input_device_index)['name']}")
        else:
            print("Input device not changed.")


def throw():
    print("hi")

if __name__ == "__main__":
    app = AudioTranscriberApp()
    keyboard.add_hotkey('command+e', app.rewrite_notes, (), trigger_on_release=False)
    app.start_recording()
    # keyboard.wait()
    app.run()
