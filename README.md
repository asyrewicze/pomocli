# pomocli
A lightweight, Terminal-native Pomodoro timer for Linux / MacOS

**pomocli** is a terminal-native Pomodoro timer for Linux and MacOS.

- 🔔 Minimal, distraction-free
- 📝 Logs your task + timestamps to a file
- 🔊 Terminal bell alert at session end
- ⏱️ Fully CLI-based, no GUI dependencies

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

You'll be prompted to enter your task, and then your 25-minute timer begins. At the end, you'll get a break timer too. Logs go to ~/pomocli_log.txt.

On Linux the filepath equates to /home/USERNAME/pomocli_log.txt

On MacOS the filepath equates to /Users/USERNAME/pomocli_log.txt

## License

MIT (See LICENSE file)
