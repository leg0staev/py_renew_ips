import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Coroutine, AsyncIterator

import aiofiles

def get_ip_addresses() -> str:
    """
    Отправляет команду ip -4 -o a и возвращает ее вывод
    :return: строковое представление того что вернула ip -4 -o a
    """
    logging.debug('получаю все ip адреса командой ip -4 -o a')
    # Выполняем команду `ip -4 -o a` и получаем вывод
    result = subprocess.run(
        ["ip", "-4", "-o", "a"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        logging.error('не мог выполнить ip -4 -o a, бросаю исключение')
        raise RuntimeError(f"Ошибка выполнения команды 'ip -4 -o a': {result.stderr}")
    logging.debug('ip адрес получил')

    return result.stdout


async def double_interface_generator(interfaces: str) -> AsyncIterator[tuple[str, str, str]]:
    """
    Принимает вывод команды 'ip -4 -o a' и генерирует интерфейсы с 2-мя ip адресами

    :param interfaces: строчное представление возвращенное командой 'ip -4 -o a'
    :yield: Кортеж (имя_интерфейса, ip_адрес_1, ip_адрес_2)
    """

    logging.debug('Поиск интерфейсов с несколькими IP-адресами')
    processed_interfaces = dict()
    for line in interfaces.splitlines():
        pts = line.split()
        name, ip = pts[1], pts[3]

        if name not in processed_interfaces:
            processed_interfaces[name] = ip
        else:
            logging.debug('')
            ip_1 = processed_interfaces.get(name)
            ip_2 = ip
            yield name, ip_1, ip_2


async def read_config(name) -> str:
    """
    Читает конфигурационный файл systemd-networkd для указанного интерфейса

    :param name: Имя сетевого интерфейса (например, 'eth0')
    :returns: Содержимое файла конфигурации
    Raises:
        IOError: При ошибках чтения файла
    """

    config_path = Path(f"/etc/systemd/network/{name}.network")

    try:
        async with aiofiles.open(config_path, mode="r", encoding="utf-8") as f:
            # Чтение всего файла сразу
            return await f.read()

    except Exception as e:
        raise IOError(f"Failed to read file {config_path}: {str(e)}")


def get_current_ip(config: str) -> str | None:
    """
    Извлекает IP-адрес из конфигурации systemd-networkd.

    :param config: Содержимое конфигурационного файла .network
    :returns: Строка с IP-адресом (например, "192.168.1.10/24")
    """

    for line in config.splitlines():
        line = line.strip()
        # Игнорируем комментарии и пустые строки
        if not line or line.startswith('#'):
            continue

        if line.startswith('Address='):
            ip = line.split('=')[1]
            return ip


def get_new_ip(old_ip: str, ip_addr_1: str, ip_addr_2: str) -> str:
    """
    Возвращает новый IP-адрес, отличный от старого.

    :param old_ip: Текущий IP-адрес
    :param ip_addr_1: Первый кандидат на замену
    :param ip_addr_2: Второй кандидат на замену
    :return: ip адрес
    """
    return ip_addr_1 if old_ip == ip_addr_2 else ip_addr_2


def get_new_gateway(ip_with_mask: str) -> str:
    """
    Генерирует gateway из IP-адреса, заменяя последний октет на '.1'.

    :param ip_with_mask: IPv4-адрес (например, "192.168.1.10/24")
    :return: Gateway (например, "192.168.1.1")
    """
    return '.'.join(ip_with_mask.split('/')[0].split('.')[:-1]) + '.1'


def get_new_table(ip_with_mask: str) -> int:
    """
    Генерирует table из IP-адреса, прибавляя предпоследний октет к 100.

    :param ip_with_mask: IPv4-адрес (например, "192.168.13.100/24")
    :return: Table (например, "113")
    """
    octet = int(ip_with_mask.split('/')[0].split('.')[-2])
    table_num = 100 + octet
    return table_num


def rewrite_config_str(config: str, ip: str, gateway: str, table_num: int) -> str:
    """
    Заменяет параметры IP, Gateway, Table и From в конфигурационной строке.

    :param config: Исходная конфигурация (многострочная строка)
    :param ip: Новый IP-адрес
    :param gateway: Новый шлюз
    :param table_num: Новый номер таблицы маршрутизации
    :return: Обновленная конфигурация
    """

    lines = config.splitlines()  # Разделяем на строки
    updated_lines = []

    for line in lines:
        if line.startswith("Address="):
            line = f"Address={ip}"
        elif line.startswith("Gateway="):
            line = f"Gateway={gateway}"
        elif line.startswith("Table="):
            line = f"Table={table_num}"
        elif line.startswith("From="):
            line = f"From={ip}"
        updated_lines.append(line)

    return '\n'.join(updated_lines)


async def write_config(interface_name: str, config_str: str) -> None:
    config_path = f'/etc/systemd/network/{interface_name}.network'
    try:
        async with aiofiles.open(config_path, mode='w', encoding='utf8') as config_file:
            await config_file.write(config_str)
    except Exception as e:
        raise IOError(f"Failed to write to file {config_path}: {str(e)}")


async def change_config(interface_name: str, first_ip: str, second_ip: str) -> None:
    conf = await read_config(interface_name)
    old_ip = get_current_ip(conf)
    real_ip = get_new_ip(old_ip, first_ip, second_ip)
    real_gateway = get_new_gateway(real_ip)
    real_table = get_new_table(real_ip)
    new_config_str = rewrite_config_str(conf, real_ip, real_gateway, real_table)
    await write_config(interface_name, new_config_str)


async def main() -> None:
    # ip_a = get_ip_addresses()

    ip_a = \
        """186: eth1    inet 192.168.11.100/24 metric 1024 brd 192.168.11.255 scope global dynamic eth0\       valid_lft 75677sec preferred_lft 75677sec
        187: eth1    inet 192.168.12.100/24 metric 1024 brd 192.168.12.255 scope global dynamic eth1\       valid_lft 75172sec preferred_lft 75172sec
        188: eth2    inet 192.168.14.100/24 metric 1024 brd 192.168.14.255 scope global dynamic eth2\       valid_lft 75171sec preferred_lft 75171sec"""

    coroutines: list[Coroutine] = []

    async for modem, ip_one, ip_two in double_interface_generator(ip_a):
        coroutines.append(change_config(modem, ip_one, ip_two))

    await asyncio.gather(*coroutines)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
