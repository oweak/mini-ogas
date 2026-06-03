@echo off
echo y | plink -pw 12345678 root@192.168.1.5 hostnamectl
echo y | plink -pw 12345678 root@192.168.1.5 "ip -4 addr show"
echo y | plink -pw 12345678 root@192.168.1.5 "df -h /"
