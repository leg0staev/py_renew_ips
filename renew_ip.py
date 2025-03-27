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
    logging.debug('вывод ip -4 -o a получил')
    logging.debug('%s', result.stdout)
    return result.stdout


async def double_interface_generator(interfaces: str) -> AsyncIterator[tuple[str, str, str]]:
    """
    Принимает вывод команды 'ip -4 -o a' и генерирует интерфейсы с 2-мя ip адресами

    :param interfaces: строчное представление возвращенное командой 'ip -4 -o a'
    :yield: Кортеж (имя_интерфейса, ip_адрес_1, ip_адрес_2)
    """

    logging.debug('Поиск интерфейсов с несколькими IP-адресами')
    processed_interfaces = {}
    for line in interfaces.splitlines():
        pts = line.split()
        name, ip = pts[1], pts[3]
        logging.debug('проверяю интерфейс %s, ip - %s', name, ip)

        if name not in processed_interfaces:
            logging.debug('интерфейс %s ранее не встречался, заношу его в словарь', name)
            processed_interfaces[name] = [ip]
        else:
            logging.debug('нашел дубликат интерфейса %s', name)
            processed_interfaces[name].append(ip)
            if len(processed_interfaces[name]) == 2:
                ip_1, ip_2 = processed_interfaces[name]
                logging.debug('возвращаю (%s, %s, %s)', name, ip_1, ip_2)
                yield name, ip_1, ip_2
            elif len(processed_interfaces[name]) > 2:
                logging.warning('Интерфейс %s имеет более двух IP-адресов', name)


async def read_config(name) -> str:
    """
    Читает конфигурационный файл systemd-networkd для указанного интерфейса

    :param name: Имя сетевого интерфейса (например, 'eth0')
    :returns: Содержимое файла конфигурации
    Raises:
        IOError: При ошибках чтения файла
    """
    logging.debug('читаю файл конфигурации для %s', name)

    config_path = Path(f"/etc/systemd/network/{name}.network")
    # config_path = Path(f"/run/media/legostaev/1gb WD blue/yandex.disk/programming/renewIPs/testfiles/{name}.network")
    logging.debug('путь для файла конфигурации - %s', config_path)

    try:
        async with aiofiles.open(config_path, mode="r", encoding="utf-8") as f:
            # Чтение всего файла сразу
            config = await f.read()
            logging.debug('файл прочитал:\n%s', config)
            return config

    except Exception as e:
        logging.error('Не смог прочитать файл %s: %s', config_path, str(e))
        raise IOError(f"Не смог прочитать файл {config_path}: {str(e)}")


def get_current_ip(config: str) -> str | None:
    """
    Извлекает IP-адрес из конфигурации systemd-networkd.

    :param config: Содержимое конфигурационного файла .network
    :returns: Строка с IP-адресом (например, "192.168.1.10/24")
    """
    logging.debug('запустил def get_current_ip, получаю текущий ip из конфига')

    for line in config.splitlines():
        line = line.strip()
        # Игнорируем комментарии и пустые строки
        if not line or line.startswith('#'):
            continue

        if line.startswith('Address='):
            logging.debug('Нашел строчку с адресом, извлекаю..')
            ip = line.split('=')[1]
            logging.debug('ip = %s', ip)
            return ip


def get_new_ip(old_ip: str, ip_addr_1: str, ip_addr_2: str) -> str:
    """
    Возвращает новый IP-адрес, отличный от старого.

    :param old_ip: Текущий IP-адрес
    :param ip_addr_1: Первый кандидат на замену
    :param ip_addr_2: Второй кандидат на замену
    :return: ip адрес
    """

    logging.debug('Запускаю def get_new_ip чтобы понять какой ip верный')
    real_ip = ip_addr_1 if old_ip == ip_addr_2 else ip_addr_2
    logging.debug('Верный IP - %s', real_ip)

    return real_ip


def get_new_gateway(ip_with_mask: str) -> str:
    """
    Генерирует gateway из IP-адреса, заменяя последний октет на '.1'.

    :param ip_with_mask: IPv4-адрес (например, "192.168.1.10/24")
    :return: Gateway (например, "192.168.1.1")
    """

    logging.debug('Запускаю def get_new_gateway чтобы понять gateway')
    gateway = '.'.join(ip_with_mask.split('/')[0].split('.')[:-1]) + '.1'
    logging.debug('gateway: %s', gateway)

    return gateway


def get_new_table(ip_with_mask: str) -> int:
    """
    Генерирует table из IP-адреса, прибавляя предпоследний октет к 100.

    :param ip_with_mask: IPv4-адрес (например, "192.168.13.100/24")
    :return: Table (например, "113")
    """
    logging.debug('Запускаю def get_new_table чтобы понять номер таблицы маршрутизации')
    octet = int(ip_with_mask.split('/')[0].split('.')[-2])
    table_num = 100 + octet
    logging.debug('верный номер таблицы маршрутизации: %d', table_num)

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
    logging.debug('изменяю исходный конфиг при помощи def rewrite_config_str')

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
    """
    Перезаписывает файл конфигурации

    :param interface_name: Имя интерфейса, для которого меняется файл конфигурации
    :param config_str: Строковое представление файла конфигурации
    :raises: OSError - ошибки записи в файл
    """
    logging.debug('Перезаписываю исходный файл при помощи def write_config')
    config_dir = '/etc/systemd/network'
    # config_dir = '/run/media/legostaev/1gb WD blue/yandex.disk/programming/renewIPs/testfiles'
    config_path = f'{config_dir}/{interface_name}.network'
    logging.debug('Путь к файлу конфигурации: %s', config_path)

    try:
        async with aiofiles.open(config_path, mode='w', encoding='utf8') as config_file:
            await config_file.write(config_str)
            logging.debug('Файл перезаписал')
    except OSError as e:
        logging.error('Ошибка записи в файл %s для интерфейса %s: %s', config_path, interface_name, str(e))
        raise OSError(f"Ошибка записи в файл {config_path} для интерфейса {interface_name}: {str(e)}")


async def change_config(interface_name: str, first_ip: str, second_ip: str) -> None:
    """
    Функция изменения файла конфигурации

    :param interface_name: Имя интерфейса, для которого меняется файл конфигурации
    :param first_ip: Первый кандидат на применение в качестве IP адреса
    :param second_ip: Второй кандидат на применение в качестве IP адреса
    """
    logging.debug('запускаю def change_config для интерфейса %s', interface_name)

    conf = await read_config(interface_name)
    old_ip = get_current_ip(conf)
    real_ip = get_new_ip(old_ip, first_ip, second_ip)
    real_gateway = get_new_gateway(real_ip)
    real_table = get_new_table(real_ip)
    new_config_str = rewrite_config_str(conf, real_ip, real_gateway, real_table)
    await write_config(interface_name, new_config_str)


async def main() -> None:
    logging.debug('запускаю def main()')
    ip_a = get_ip_addresses()

    coroutines: list[Coroutine] = []

    async for modem, ip_one, ip_two in double_interface_generator(ip_a):
        coroutines.append(change_config(modem, ip_one, ip_two))

    await asyncio.gather(*coroutines)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
