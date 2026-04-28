import os
print("----------------------"); print("| TQSync Auto Pusher |"); print("----------------------"); print("1.版本号处理"); print("major,minor,patch")
bump_type = input("what do u want to bump: ")
if bump_type == "major":
    os.system("python ./utils/version_bumper.py -major")
elif bump_type == "minor":
    os.system("python ./utils/version_bumper.py -minor")
elif bump_type == "patch":
    os.system("python ./utils/version_bumper.py -patch")
else:
    print("未知输入内容，未做版本号更改")
print("2.Git Commit")
os.system("git add .")
os.system("git commit ")
print("3.Git Push")
os.system("git push origin Next")