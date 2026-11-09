# Security

## Read this before you run it

The server has **no login and no encryption**. Anyone who can reach its port can move your faders, mute channels
and change names. That is intended for a closed network (a stage or studio network, or a hotspot of its own).

- **Do not expose it to the internet** (no port forwarding, no public hosting).
- On a shared or guest network, put it on a separate network, or restrict access to the Pi with a firewall.
- The page never asks for or stores passwords. The only file it writes is `names.json`, with the names you typed.

## Reporting a vulnerability

Please report security problems **privately**, using GitHub's *Report a vulnerability* button under the
repository's **Security** tab, not as a public issue. I will answer as soon as I can; this is a hobby project
maintained by one person, so please be patient.

Only the latest version on the `main` branch is supported.
