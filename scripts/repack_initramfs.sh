#!/bin/bash
set -e
# Dependencies:
# sudo apt-get install -y cpio fakeroot tar u-boot-tools gzip

# Function to display usage information
usage() {
    echo "Usage: $0 <initramfs.bin.SD> <new-files.tgz> [image-name] [output-filename] "
    echo "  <initramfs.bin.SD>  - The original RAMDisk Image file"
    echo "  <new-files.tgz>     - The tarball containing new files and optionally delete.list.txt"
    echo "  [image-name]        - The optional name for the mkimage image (default: Angstrom-opkg_m-eglibc-ipk-v)"
    echo "  [output-filename]   - The optional name for the output initramfs file (default: new_initramfs.bin.SD)"
    exit 1
}

# Check if the correct number of arguments are provided
if [ "$#" -lt 2 ] || [ "$#" -gt 5 ]; then
    usage
fi

# Assign arguments to variables
INITRAMFS=$(readlink -f "$1")
NEW_FILES=$(readlink -f "$2")
IMAGE_NAME="${3:-Angstrom-opkg_m-eglibc-ipk-v}"  # Default to given image name if not provided
OUTPUT_FILENAME="$(readlink -f ${4:-new_$(basename $1)})"  # Default to new_initramfs.bin.SD if not provided
TEMP_DIR=$(mktemp -d)
CPIO_FILENAME="rootfs.cpio.gz"  # Default to given cpio filename if not provided
ORIG_CPIO="$TEMP_DIR/$(basename "$CPIO_FILENAME" .cpio.gz).orig.cpio.gz"
ORIG_CPIO_FILENAME="$TEMP_DIR/$(basename "$ORIG_CPIO" .gz)"
UNPACK_DIR="$TEMP_DIR/unpacked"
FAKEROOT_FILE="$TEMP_DIR/.fakeroot"
NEW_FILES_OUTPUT="$TEMP_DIR/new_files"
NEW_CPIO="$TEMP_DIR/$CPIO_FILENAME"
NEW_INITRAMFS="$TEMP_DIR/new_initramfs.gz"

# Ensure the temporary directory was created
if [ ! -d "$TEMP_DIR" ]; then
    echo "Failed to create temporary directory."
    exit 1
fi
echo "Temporary directory created: $TEMP_DIR"

# Extract the original initramfs
tail -c+65 < "$INITRAMFS" > "$ORIG_CPIO"
gunzip "$ORIG_CPIO"

# Create a directory for unpacking
mkdir "$UNPACK_DIR"
cd "$UNPACK_DIR" || exit

# Extract the cpio file and create a fakeroot
cat "$ORIG_CPIO_FILENAME" | fakeroot -s "$FAKEROOT_FILE" cpio -idmv

# Extract new files and handle deletions
tar -xvzf $NEW_FILES -C "$TEMP_DIR" ./delete.list.txt 2> /dev/null

# Check if delete.list.txt exists and remove listed files
if [ -f "$TEMP_DIR/delete.list.txt" ]; then
    echo "Deleting files from the initramfs..."
    while IFS= read -r file; do
        if [ -e "$file" ]; then
            fakeroot -i "$FAKEROOT_FILE" rm -rfv "$file"
        else
            echo "Warning: File $file not found, skipping."
        fi
    done < "$TEMP_DIR/delete.list.txt"
fi

# Merge new files into the unpacked directory, excluding delete.list.txt
echo "Adding new files to the initramfs..."
fakeroot -i $FAKEROOT_FILE -s $FAKEROOT_FILE tar --exclude='delete.list.txt' -xvzf "$NEW_FILES" -C "$UNPACK_DIR"

# Repack the cpio file
echo "Repacking the cpio file..."
sh -c 'find . | fakeroot -i '"$FAKEROOT_FILE"' cpio -H newc -o' | gzip -9 > "$NEW_CPIO"

# Create new initramfs
mkimage -A arm -O linux -T ramdisk -n "$IMAGE_NAME" -d "$NEW_CPIO" "$OUTPUT_FILENAME"

# Cleanup
echo "Cleaning up temporary files in $TEMP_DIR..."
rm -rf "$TEMP_DIR"

echo "Initramfs repacking complete. Output file: $OUTPUT_FILENAME"