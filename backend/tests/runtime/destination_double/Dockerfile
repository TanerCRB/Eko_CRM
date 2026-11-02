# syntax=docker/dockerfile:1
# The backup destination double (ADR-0004 addendum 2026-10-30): test harness only, never in
# compose.yaml. An OpenSSH server whose every session is forced through the recorder, which logs
# each SFTP request and hands it to sftp-server with the destination's flags.
FROM python:3.12.16-slim-trixie
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      openssh-server=1:10.0p1-7+deb13u4 \
      openssh-sftp-server=1:10.0p1-7+deb13u4 \
      openssh-client=1:10.0p1-7+deb13u4 \
      age=1.2.1-1+b5 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --no-create-home --home-dir /incoming --shell /bin/sh eko-backup \
 && usermod -p '*' eko-backup \
 && mkdir -p /incoming /etc/ssh/authorized_keys /etc/eko-double /var/log/eko-double /run/sshd /keys \
 && chown eko-backup /incoming && chmod 0300 /incoming \
 && chmod 0700 /keys \
 && touch /var/log/eko-double/access.jsonl && chmod 0666 /var/log/eko-double/access.jsonl \
 && echo on > /etc/eko-double/mode
COPY --chmod=0644 sshd_config /etc/ssh/sshd_config
COPY --chmod=0755 recorder.py /usr/local/bin/eko-double-recorder
COPY --chmod=0755 start.sh /usr/local/bin/eko-double-start
COPY --chmod=0644 it-destination-fragment.conf /etc/eko-double/it-destination-fragment.conf
ENTRYPOINT ["/usr/local/bin/eko-double-start"]
