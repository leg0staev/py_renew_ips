# Скрипт обновления конфигурационных файлов lte модемов на python

ранее я уже делал подобный скрипт [на bash](https://github.com/leg0staev/renewIPs/tree/main#). Но мне больше по душе python.

скрипт читает вывод команды ```ip -4 -o a``` и изменяет конфигурационные файлы в ```/etc/systemd/network```

Имею несколько модедемов в одном usb хабе. Каждый раз после их перезагрузки, система перемешивает их имена. При этом IP адреса и DHCP жестко настроены в настроках модемов. Получается что модемы меняются файлами настроек IP, которые не совпадают с тем что настроено внутри них<br>

команда ```ip -4 -o a``` выводит примерно следующее:<br>
```31: eth1    inet 192.168.8.100/24 metric 1024 brd 192.168.8.255 scope global dynamic eth1\       valid_lft 86399sec preferred_lft 86399sec```<br>
```32: eth1    inet 192.168.15.100/24 metric 1024 brd 192.168.15.255 scope global dynamic eth1\       valid_lft 86399sec preferred_lft 86399sec```<br>
```33: eth2    inet 192.168.13.100/24 metric 1024 brd 192.168.13.255 scope global dynamic eth2\       valid_lft 86399sec preferred_lft 86399sec```<br>
```34: eth2    inet 192.168.17.100/24 metric 1024 brd 192.168.17.255 scope global dynamic eth2\       valid_lft 86399sec preferred_lft 86399sec```<br>
```35: eth4    inet 192.168.12.100/24 metric 1024 brd 192.168.12.255 scope global dynamic eth4\       valid_lft 86399sec preferred_lft 86399sec```<br>
```36: eth5    inet 192.168.14.100/24 metric 1024 brd 192.168.14.255 scope global dynamic eth5\       valid_lft 86399sec preferred_lft 86399sec```<br>

Интефейсы задвоены, одна настройка от DHCP модема, вторая из файла конфигурации в системе.<br>

Скрипт читает вывод ```ip -4 -o a``` запоминает IP если интерфейс дублируется, читает файл конфига в ```/etc/systemd/network```, понимает какой адрес актуален и меняет конфиг.
