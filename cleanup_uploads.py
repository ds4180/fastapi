import os
import shutil
import sys

# Get UPLOAD_DIR from environment variable or default to 'uploads'
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

def total_wipeout():
    if not os.path.exists(UPLOAD_DIR):
        print(f"Directory [{UPLOAD_DIR}] already does not exist.")
        return

    print(f"CRITICAL WARNING: Deleting EVERYTHING inside and including [{UPLOAD_DIR}]...")
    
    # 1. Try to delete the entire directory tree
    try:
        # If it's a mount point, we delete everything inside it
        for item in os.listdir(UPLOAD_DIR):
            item_path = os.path.join(UPLOAD_DIR, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"Deleted folder: {item_path}")
            else:
                os.unlink(item_path)
                print(f"Deleted file: {item_path}")
        
        # 2. Try to delete the root uploads folder itself
        try:
            os.rmdir(UPLOAD_DIR)
            print(f"Deleted root directory: {UPLOAD_DIR}")
        except OSError:
            # This happens if it's a Docker mount point (cannot delete the mount itself)
            print(f"Note: Root [{UPLOAD_DIR}] remains as it might be a mount point, but it is now EMPTY.")

        print("-" * 30)
        print("SUCCESS: All upload folders and files have been removed.")

    except Exception as e:
        print(f"Error during wipeout: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        total_wipeout()
    else:
        answer = input("DANGER: This will delete ALL folders and files. Proceed? (y/n): ")
        if answer.lower() == 'y':
            total_wipeout()
        else:
            print("Operation cancelled.")
