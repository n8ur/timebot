SOURCE_DIR="/usr/local/lib/timebot/bin"
TARGET_DIR="/usr/local/bin"

# Ensure the source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: Source directory '$SOURCE_DIR' not found."
else
  # Loop through all items in the source directory
  for filepath in "$SOURCE_DIR"/*; do
    # Check if the item is a regular file
    if [ -f "$filepath" ]; then
      filename=$(basename "$filepath")
      echo "Creating symlink: $TARGET_DIR/$filename -> $filepath"
      sudo ln -sf "$filepath" "$TARGET_DIR/$filename"
    else
      echo "Skipping '$filepath' (not a regular file)."
    fi
  done
  echo "Symlink creation process complete."
fi

