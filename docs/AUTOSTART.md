# Start on boot (Raspberry Pi, systemd)

This sets the server up as a systemd service. It starts at power-on without anyone logging in, waits until the
01V96 is connected and its MIDI port exists, and restarts itself if it stops.

The unit file is [mixer-web.service](../mixer-web.service). It assumes:

| Item | Value in the unit file |
|---|---|
| Service user | `yamaha` (member of `audio`) |
| Project folder | `/opt/01v96/yamaha-remote` |
| Python | `/opt/01v96/yamaha-remote/.venv` |
| Port | `8000`, listening on `0.0.0.0` |
| MIDI port name | `MIDI_PORT=01V96` |

Change these in the file if your setup differs. `WorkingDirectory` and the path in `ExecStart` must point to the
same folder, the one that contains `server/` and `requirements.txt`.

## 1. Install the prerequisites

```bash
sudo apt install python3-venv alsa-utils      # alsa-utils provides aconnect, used by the wait loop
```

## 2. Create the service user (optional)

You can use your normal login user instead. If you do, set `User=` and `Group=` in the unit file to that name.

```bash
sudo useradd --system --create-home --home-dir /opt/01v96 --shell /usr/sbin/nologin --groups audio yamaha
```

The `audio` group is required: the user must be allowed to open the MIDI device.

## 3. Put the project in place

```bash
sudo cp -r <path-to-this-project> /opt/01v96/yamaha-remote
sudo chown -R yamaha:yamaha /opt/01v96/yamaha-remote
sudo -u yamaha python3 -m venv /opt/01v96/yamaha-remote/.venv
sudo -u yamaha /opt/01v96/yamaha-remote/.venv/bin/pip install -r /opt/01v96/yamaha-remote/requirements.txt
```

The service user must own the project folder, because the app writes `names.json` there.

## 4. Install and enable the service

```bash
sudo cp /opt/01v96/yamaha-remote/mixer-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mixer-web.service
```

`enable` makes it start at every boot, `--now` also starts it immediately.

## 5. Check that it works

```bash
systemctl status mixer-web
aconnect -l | grep -i 01v96          # the mixer must be listed
curl -I http://localhost:8000/
```

Then reboot (`sudo reboot`) and open `http://<address of the Pi>:8000` from a device on the same network.
With the Pi's own hotspot (NetworkManager default) that is `http://10.42.0.1:8000`.

Test both cases once: mixer on before the Pi boots, and mixer switched on after the Pi is up.

## How it behaves

- **Mixer not connected at boot:** the status shows `activating (start-pre)`. The unit polls `aconnect -l`
  every 2 seconds and has no start timeout, so it starts as soon as the mixer appears.
- **Server crashes:** `Restart=on-failure` starts it again after 3 seconds.
- **Mixer unplugged while running:** the server is not stopped automatically. Restart it with
  `sudo systemctl restart mixer-web` after reconnecting, or add a udev rule that does this for you.

## Day-to-day commands

```bash
sudo systemctl restart mixer-web       # after updating the code
sudo systemctl stop mixer-web
sudo systemctl disable mixer-web       # do not start at boot
journalctl -u mixer-web -f             # live log
journalctl -u mixer-web -b --no-pager  # log of this boot
```

After editing the unit file, copy it to `/etc/systemd/system/` again and run `sudo systemctl daemon-reload`.

## Troubleshooting

| Log message | Cause and fix |
|---|---|
| `status=200/CHDIR`, `Changing to the requested working directory failed` | `WorkingDirectory` does not exist. Check with `sudo ls /opt/01v96/yamaha-remote`. |
| `status=203/EXEC` | The path in `ExecStart` is wrong, or `.venv` was not created. |
| `status=217/USER` | The user in `User=` does not exist (`id yamaha`). |
| Stuck in `activating (start-pre)` | The mixer is not detected. Check the USB cable and `aconnect -l`. If the port name does not contain `01v96`, change the `grep` pattern. If `aconnect` is missing, install `alsa-utils`. |
| `No MIDI port matching ...` | The `MIDI_PORT` value does not match a port name. Compare with `python -c "import mido; print(mido.get_output_names())"`. |
| `Permission denied` on the MIDI device | The service user is not in the `audio` group (`id yamaha`). |
| Page not reachable from other devices | The unit must use `--host 0.0.0.0`. Check the Pi's address with `hostname -I`. |
