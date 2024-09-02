WIP

# Muesli

This project is aiming to develop a simple tool to help with autocompleting notes while in meetings.

Inspired by [Granola](https://granola.so/), this project is aiming to be a simpler, open-source version of the same idea. The key difference is that I want to be able to rewrite my notes using AI and my microphone _while in a meeting_, not just afterwards.

The dream would be: [Copilot](https://github.com/features/copilot) or [Cursor](https://www.cursor.com/) for notes. E.g. while writing, seeing an autocompletion and being able to \[tab\] to accept it.

On the way there, we can just use keyboard shortcuts to insert the completed text wherever you are, or we can make a pop-up show the text, making it easy to select+copy+paste

Plan:
1. Paste the last 30s-5m of audio from my microphone/computer into a text box (for those moments where you're like "Wow! You said that so well! I wish we had that written down!") 
2. Complete the notes you have written already, using the transcript (from 1) and an LLM (gpt-4o).
3. Build out the autocomplete UI

Because this is open source / running locally, you can trust that the recording is only stored locally in-memory until you choose to transcribe the recent bits. We can use a queue to just automatically delete audio once it's ~5m old.

As a principle, we can also make everything customizable, including prompts.