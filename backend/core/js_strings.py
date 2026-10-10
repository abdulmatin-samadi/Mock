"""Texts the JavaScript shows (save state, recorder, mistakes notebook). They are translated on the
server and handed to the page as JSON — see {% js_i18n %} and DreamZone.t() in app.js."""
from django.utils.translation import gettext_noop as N

JS_STRINGS = [
    # exam room
    N("Unsaved changes"), N("Saving…"), N("All answers saved"), N("Offline — will retry"), N("Submitting…"),
    N("✓ Submit Test"), N("Could not submit:"), N("Time is up — submitting…"),
    # writing
    N("Draft saved"), N("Draft kept on this device — will retry"), N("Submit for evaluation"), N("word"),
    N("words"),
    # speaking
    N("Microphone permission was denied. Allow microphone access in your browser and try again."),
    N("Preparation time"), N("Review your answer"), N("The recording is empty. Please record again."),
    N("Uploading…"), N("Saved. The AI is transcribing and evaluating it in the background."), N("Upload failed:"),
    N("Finishing…"), N("Finish test"), N("Time is up. Submit any recorded answer, then finish the test."),
    N("answered"), N("Recording — speak now"),
    # mistakes notebook / "Why?"
    N("✨ AI is writing an explanation…"), N("Teacher's note"), N("✨ AI explanation"), N("Answer"), N("Correct!"),
    N("Not quite — try again."),
]
