import sqlite3
import docker

DATABASE = '/etc/scripts/bot_data.db'  # Укажите путь к базе данных

import docker
import os

# Создание клиента Docker
client = docker.from_env()

def backup_container(container_id, backup_path):
    """
    Создает бэкап контейнера в виде tar-архива.
    
    :param container_id: ID контейнера.
    :param backup_path: Путь для сохранения бэкапа.
    """
    try:
        container = client.containers.get(container_id)
        with open(backup_path, 'wb') as backup_file:
            # Экспорт контейнера
            bits = container.export()
            for chunk in bits:
                backup_file.write(chunk)
        print(f"Бэкап контейнера {container_id} успешно создан: {backup_path}")
    except Exception as e:
        print(f"Ошибка при создании бэкапа контейнера {container_id}: {e}")

def backup_volume(volume_name, backup_path):
    """
    Создает бэкап тома Docker.
    
    :param volume_name: Имя тома Docker.
    :param backup_path: Путь для сохранения бэкапа.
    """
    try:
        volume = client.volumes.get(volume_name)
        container = client.containers.run(
            image="alpine",  # Легкое окружение для копирования данных
            command=f"tar -czf - -C /volume .",
            volumes={volume.name: {'bind': '/volume', 'mode': 'ro'}},
            detach=True,
            remove=True
        )
        with open(backup_path, 'wb') as backup_file:
            for chunk in container.logs(stream=True):
                backup_file.write(chunk)
        print(f"Бэкап тома {volume_name} успешно создан: {backup_path}")
    except Exception as e:
        print(f"Ошибка при создании бэкапа тома {volume_name}: {e}")

def backup_all_containers(backup_dir):
    """
    Создает бэкапы для всех запущенных контейнеров.
    
    :param backup_dir: Директория для хранения бэкапов.
    """
    containers = client.containers.list()  # Получить все контейнеры

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    for container in containers:
        container_backup_path = os.path.join(backup_dir, f"{container.name}_backup.tar")
        backup_container(container.id, container_backup_path)
        print(f"Бэкап для контейнера {container.name} завершен.")

def restore_container(backup_path, new_container_name, ports=None):
    """
    Восстанавливает контейнер из бэкапа.
    
    :param backup_path: Путь к файлу бэкапа.
    :param new_container_name: Имя для нового контейнера.
    :param ports: Словарь портов (например, {'443/tcp': 8443}).
    """
    try:
        with open(backup_path, 'rb') as backup_file:
            image = client.images.load(backup_file.read())[0]

        container = client.containers.run(
            image=image,
            name=new_container_name,
            ports=ports,
            detach=True
        )
        print(f"Контейнер {new_container_name} успешно восстановлен.")
        return container
    except Exception as e:
        print(f"Ошибка при восстановлении контейнера из {backup_path}: {e}")

def backup_all_volumes(backup_dir):
    """
    Создает бэкапы всех томов Docker.
    
    :param backup_dir: Директория для хранения бэкапов.
    """
    volumes = client.volumes.list()

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    for volume in volumes:
        volume_backup_path = os.path.join(backup_dir, f"{volume.name}_backup.tar.gz")
        backup_volume(volume.name, volume_backup_path)
        print(f"Бэкап для тома {volume.name} завершен.")

if __name__ == "__main__":
    # Пример использования
    backup_directory = "./backups"

    print("Создание бэкапов всех контейнеров...")
    backup_all_containers(backup_directory)

    print("Создание бэкапов всех томов...")
    backup_all_volumes(backup_directory)

    # Пример восстановления
    # restore_container("./backups/container_backup.tar", "restored_container", ports={"443/tcp": 8443})
