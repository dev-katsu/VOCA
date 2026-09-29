
with open("detector.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("        try:\n\n        try:", "        try:")
text = text.replace("        try:\n        try:", "        try:")
with open("detector.py", "w", encoding="utf-8") as f:
    f.write(text)

