"""
sudo apt-get update

# Git credential
sudo apt-get install -y git make gcc libsecret-1-0 libsecret-1-dev libglib2.0-dev
ls -al /usr/share/doc/git/contrib/credential/libsecret || true
sudo make -C /usr/share/doc/git/contrib/credential/libsecret


"""

"""
How to connect to Git repo

1. Git/SSH installation + Git user config

sudo apt-get update
sudo apt-get install -y git openssh-client

git config --global user.name  "YOUR_NAME"
git config --global user.email "YOUR_EMAIL"

2. SSH key generation

mkdir -p ~/.ssh
chmod 700 ~/.ssh

ssh-keygen -t ed25519 -C "nodi-inc" -f ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub

3. Register SSH public key to github

cat ~/.ssh/id_ed25519.pub

> GitHub web login
> Settings → SSH and GPG keys → New SSH key
> Paste public key and save

4. Register github to known_hosts

ssh-keyscan -H github.com >> ~/.ssh/known_hosts
chmod 644 ~/.ssh/known_hosts

5. SSH authentication test

ssh -T git@github.com

6. (Option) If already logged in with HTTPS, change to SSH

cd MY_REPO
git remote set-url origin git@github.com:MY_USER/MY_REPO.git
git remote -v



"""