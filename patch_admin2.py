import re

with open("cogs/admin.py", "r") as f:
    content = f.read()

content = content.replace('f"Git pull failed:\\n```{stderr.decode()}```"', 'f"Git pull failed:\\n```\\n{stderr.decode()}\\n```"')
content = content.replace('f"Dependency install failed:\\n```{stderr.decode()}```"', 'f"Dependency install failed:\\n```\\n{stderr.decode()}\\n```"')

with open("cogs/admin.py", "w") as f:
    f.write(content)
