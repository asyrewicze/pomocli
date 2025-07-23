# pomocli

A lightweight, Terminal-native Pomodoro timer for Linux / MacOS

**pomocli** is a terminal-native Pomodoro timer for Linux and MacOS.

- Minimal, distraction-free
- Logs your task + timestamps to a file
- Terminal bell alert at session end
- Fully CLI-based, no GUI dependencies

## Usage

Make sure the script is executable:

```bash
chmod +x pomocli
```

Then, simply running:

```bash
./pomocli
```

should be all that's needed, assuming your Python PATHing is correct. Otherwise you can call Python directly:

```bash
python3 pomocli
```

You'll be prompted to enter your task, and then your 25-minute timer begins. At the end, you'll get a break timer too. 

## Task Logging

Logs go to ~/pomocli_log.txt.

On Linux the filepath equates to /home/USERNAME/pomocli_log.txt

On MacOS the filepath equates to /Users/USERNAME/pomocli_log.txt

## Making pomocli Globally Available

To run pomocli from any terminal without typing python3, you can install it into your system's PATH.

### On Linux

Move the script to a directory that's in your PATH, like /usr/local/bin:

```bash
sudo mv pomocli /usr/local/bin/
```

Now you can run:

```bash
pomocli
```

Right from the CLI!

### On MacOS

#### Option A: Use a personal ~/bin directory

1. Create the directory if it doesn't exist:

```bash
mkdir -p ~/bin
```

2. Move the script there:

```bash
mv pomocli ~/bin/
```

3. Add ~/bin to your shell PATH if it isn’t already:

For Zsh (default on macOS):

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

For Bash:

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
```

#### Option B: Use /opt/homebrew/bin (Apple Silicon Macs)

```bash
sudo mv pomocli /opt/homebrew/bin/
```

Or symlink it:

```bash
ln -s /full/path/to/pomocli /opt/homebrew/bin/pomocli
```

You can now run:

```bash
pomocli
```

from any terminal session!

## License

MIT (See LICENSE file)
