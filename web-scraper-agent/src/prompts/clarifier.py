CLARIFIER = """The user wrote this task: {task}

Page snapshot: {html}

If the task is ambiguous, ask ONE short clarifying question so you can build an accurate script.
If it is already clear, reply with "OK".

Examples of good questions:
- Should I extract all product names or only discounted ones?
- Do you need the images downloaded or just their URLs?
- What format do you prefer: CSV or JSON?

Reply in plain text, max 20 words.
"""