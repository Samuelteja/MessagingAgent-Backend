import os

def list_files(base_path):
    for root, dirs, files in os.walk(base_path):
        # Skip __pycache__ directories
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")

        # Print each file path
        for file in files:
            print(os.path.relpath(os.path.join(root, file), base_path))


if __name__ == "__main__":
    base_dir = r"C:\Users\sloda\Downloads\Codeforces\MessagingAgent\src"
    list_files(base_dir)
