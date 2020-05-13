from ftplib import FTP, error_perm
from typing import *
import hashlib
import os
from glob import glob
import json
from getpass import getpass

# files and folders not to remove
permanent_files = ["info.php", ".gitkeep"]
permanent_folders = ["subdom", "domains"]

# files and folders to ignore when uploading
ignored_files = []
ignored_folders = ["scripts"]

checksum_file_name = "checksum.json"

website_ftp_folder = "www"

# a debug flag for only printing which files and folders will be changed
DEBUG = True


def remove_content(old: Dict[str, str], new: Dict[str, str]):
    """Removes all relevant content on the FTP server."""
    # for all subdirectories of the current directory
    for content in ftp.nlst():
        # a very not-pretty way to determine if a path is a file or not
        # a little slow but probably better than anything else
        # see https://stackoverflow.com/questions/1088336/ftplib-checking-if-a-file-is-a-folder
        is_file = True
        try:
            ftp.size(content)
        except Exception as e:
            is_file = False

        # get the folder/file path relative to the website ftp folder
        relative_path = (ftp.pwd() + "/" + content)[len(website_ftp_folder) + 2 :]

        # if it's a file
        if is_file:
            # and the content isn't permanent
            if (
                content not in permanent_files
                and not hashsums_match(old, new, relative_path)
            ):
                # if it's a file, delete it
                if not DEBUG:
                    ftp.delete(content)
                print("DELETED FILE:\t\t" + ftp.pwd() + "/" + content)

        elif content not in permanent_folders:
            # move down to the directory and recursively call remove_content
            ftp.cwd(content)
            remove_content(old, new)

            remaining_files = len(ftp.nlst())
            ftp.cwd("..")

            if remaining_files == 0:
                if not DEBUG:
                    ftp.rmd(content)
                print("DELETED DIRECTORY:\t" + ftp.pwd() + "/" + content)


def add_content(old: Dict[str, str], new: Dict[str, str]):
    """Add the content of the current folder to the website."""
    # get all directories
    directories = []
    for directory, _, _ in os.walk("."):
        stripped_directory = directory[2:]

        if stripped_directory != "" and stripped_directory not in ignored_folders:
            # the replace is for windows' paths
            directories.append(stripped_directory.replace(os.sep, "/"))

    # upload (create) all directories first
    for directory in sorted(directories):
        # a hack for only creating non-existent directories
        try:
            pwd = ftp.pwd()
            ftp.cwd(directory)
            ftp.cwd(pwd)
        except Exception as e:
            if not DEBUG:
                ftp.mkd(directory)
            print("CREATED DIRECTORY:\t" + directory)

    # upload files...
    for file in new:
        # that are not ignored and didn't match hashsums
        if file not in ignored_files and not hashsums_match(old, new, file):
            if not DEBUG:
                ftp.storbinary("STOR " + file, open(file, "rb"))
            print("CREATED FILE:\t\t" + file)


def hashsums_match(old, new, key):
    return key in old and key in new and old[key] == new[key]

def generate_hashsum(file_name):
    """Generate a SHA-256 hashsum of the given file."""
    hash_sha256 = hashlib.sha256()

    with open(file_name, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)

    return hash_sha256.hexdigest()


def get_list_of_files():
    """Return the list of files in the current directory."""
    return [
        os.path.join(root, name)[2:]
        for root, dirs, files in os.walk(".")
        for name in files
    ]


def get_hashsum_file():
    return {f: generate_hashsum(f) for f in get_list_of_files()}


# read credentials
ip = None
login = None
password = None

try:
    from login import *

    print("login.py found, loading saved credentials.")

    assert ip is not None, "IP not set."
    assert login is not None, "Login not set."
    assert password is not None, "Password not set."

except ImportError as e:
    print("login.py not found, enter credentials manually.")

    ip = input("IP: ")
    login = input("login: ")
    password = getpass("password: ")


# change to the _site directory
os.chdir(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "_site"))


print(f"Connecting to {ip}...")
with FTP(ip, login, password) as ftp:
    FTP.maxline = 16384 #TODO

    print(ftp.cwd(website_ftp_folder))

    new = get_hashsum_file()
    json.dump(new, open(checksum_file_name, "w"))

    # get the old hashsum
    old = {}
    if checksum_file_name in ftp.nlst():
        # get the old checksum by reading the file on the server
        lines = []
        ftp.retrlines(f"RETR {checksum_file_name}", lambda x: lines.append(x))

        old = json.loads("\n".join(lines))

    # remove all content that isn't permanent
    remove_content(old, new)

    # add all content from _site folder which is not ignored
    add_content(old, new)

    # disconnect from the server and terminate the script
    print(ftp.quit())
    quit()
