import subprocess
import sys

def run(cmd, capture=False):
    """Run a command, optionally capturing stderr. All goes to terminal."""
    kwargs = {}
    if capture:
        kwargs["stderr"] = subprocess.PIPE
        kwargs["stdout"] = subprocess.PIPE
        kwargs["text"] = True
        result = subprocess.run(cmd, shell=True, **kwargs)
        if result.returncode != 0:
            err = result.stderr.strip() if result.stderr else ""
            out = result.stdout.strip() if result.stdout else ""
            print(err or out or "command failed")
        return result.returncode
    else:
        return subprocess.run(cmd, shell=True).returncode

print("----------------------")
print("| TQSync Auto Pusher |")
print("----------------------")
print("1.版本号处理")
print("major,minor,patch")
bump_type = input("what do u want to bump: ")
if bump_type == "major":
    run("python ./utils/version_bumper.py -major")
elif bump_type == "minor":
    run("python ./utils/version_bumper.py -minor")
elif bump_type == "patch":
    run("python ./utils/version_bumper.py -patch")
else:
    print("未知输入内容，未做版本号更改")

print("2.Git Commit")
ret = run("git add .")
if ret != 0:
    print("git add failed")
    sys.exit(1)

ret = run("git commit")
if ret != 0:
    print("git commit failed (commit aborted or no changes)")
    sys.exit(1)

print("3.Git Push")
ret = run("git push", capture=True)
if ret != 0:
    print("git push failed — see error above")
    sys.exit(1)