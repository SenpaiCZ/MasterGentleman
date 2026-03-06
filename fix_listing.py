import sys

with open('views/listing.py', 'r') as f:
    content = f.read()

# We need to make sure we don't exceed the row limit of 5.
# And maybe limit the number of costumes to prevent API crash.

# Find the chunking logic:
target = """            chunk_size = 24
            chunks = [self.available_costumes[i:i + chunk_size] for i in range(0, len(self.available_costumes), chunk_size)]

            for index, chunk in enumerate(chunks):"""

replacement = """            chunk_size = 24

            # Prevent more chunks than we can fit.
            # We have row_offset currently at maybe 2. So we have 3 rows left (2, 3, 4).
            # 1 row is needed for Account Select (if any), 1 row is needed for action buttons.
            # No, action buttons don't have a row anymore? They were added earlier with `.row` set!
            # Oh, wait! The action buttons were added to `buttons` array, taking row 0 and 1.
            # So row 2, 3, 4 are totally free for Selects.
            # Account select takes 1 row, leaving 2 rows for Costumes (and maybe 1 for Variant Select).
            # Let's just limit costumes chunks to 2, or maximum available rows.
            max_chunks = 2
            chunks = [self.available_costumes[i:i + chunk_size] for i in range(0, len(self.available_costumes), chunk_size)][:max_chunks]

            for index, chunk in enumerate(chunks):"""

if target in content:
    content = content.replace(target, replacement)
    with open('views/listing.py', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
