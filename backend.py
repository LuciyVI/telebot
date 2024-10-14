import docker,requests
from requests.auth import HTTPBasicAuth
import re

async def create_openvpn_config(trial=False):
    """
    Генерация OpenVPN конфигурации с подстановкой корректных портов и IP-адресов.
    Включает аутентификацию с использованием имени пользователя и пароля, получаемого из логов контейнера.
    """
    client = docker.from_env()

    # Получаем ID последнего запущенного контейнера
    container_id = (await get_running_containers_info('id'))[-1]
    container = client.containers.get(container_id)

    # Получаем информацию о портах контейнера
    container_ports = container.attrs['NetworkSettings']['Ports']
    
    # Получаем значение внешнего UDP порта
    internal_port_udp = f"{1194}/udp"
    connect_port_udp = container_ports.get(internal_port_udp, [])
    connect_port_udp_value = connect_port_udp[0]['HostPort'] if connect_port_udp else None

    # Получаем значение внешнего TCP порта
    internal_port_tcp = f"{443}/tcp"
    connect_port_tcp = container_ports.get(internal_port_tcp, [])
    connect_port_tcp_value = connect_port_tcp[0]['HostPort'] if connect_port_tcp else None
    
    # Внутренний IP адрес контейнера
    internal_ip = container.attrs['NetworkSettings']['IPAddress']

    # URL для обращения к контейнеру по API
    url = f'https://0.0.0.0:{connect_port_tcp_value}/rest/GetGeneric'
    
    # Дефолтное имя пользователя OpenVPN
    username = 'openvpn'
    
    # Получаем автоматически сгенерированный пароль из логов контейнера
    password = await parse_container_logs_for_password(container_id)

    # Выполняем запрос к API контейнера для получения исходной конфигурации
    response = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
    payload = response.content.decode('utf-8')

    # Заменяем внутренний IP контейнера на внешний IP сервера
    modified_payload = payload.replace(internal_ip, '109.120.179.155')
    
    # Подставляем внешние порты
    if connect_port_udp_value:
        modified_payload = modified_payload.replace('1194', connect_port_udp_value)
    if connect_port_tcp_value:
        modified_payload = modified_payload.replace('443', connect_port_tcp_value)

    # Очищаем конфигурацию от комментариев и ненужных строк
    cleaned_payload = '\n'.join([line for line in modified_payload.splitlines() if not line.strip().startswith('#')])

    # Убираем строку "auth-user-pass" из конфигурации
    cleaned_payload = re.sub(r'auth-user-pass', '', cleaned_payload, flags=re.DOTALL)

    # Добавляем секцию с аутентификацией
    auth_user_pass = f"""
pull-filter ignore "dhcp-pre-release"
pull-filter ignore "dhcp-renew"
pull-filter ignore "dhcp-release"
pull-filter ignore "register-dns"
pull-filter ignore "block-ipv6"
<auth-user-pass>
openvpn
{password}
</auth-user-pass>
"""
    
    # Формируем финальную конфигурацию
    final_payload = cleaned_payload + "\n" + auth_user_pass.strip()
    
    # Кодируем строку в байты для отправки как файл
    encoded_payload = final_payload.encode('utf-8')
    
    return encoded_payload


async def get_running_containers_info(type_info):
    client = docker.from_env()
    containers_info = []

    containers = client.containers.list()

    for container in containers:
        container_data = {
            'id': container.short_id,
            'name': container.name,
            'ports': container.ports,
            'status': container.status,
            'image': container.image.tags
        }

        if type_info in container_data:
            containers_info.append(container_data[type_info])
        else:
            containers_info.append(None)

    return containers_info

def block_container_access(container_id):
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        container.stop()
        # Update the database to indicate that access has been blocked
        conn = sqlite3.connect(DATABASE)
        conn.execute('''
            UPDATE users SET access_blocked = 1 WHERE container_id = ?
        ''', (container_id,))
        conn.commit()
        print(f"Access to container {container_id} has been blocked after the trial period.")
    except Exception as e:
        print(f"Error stopping container {container_id}: {e}")

async def parse_container_logs_for_password(container_id):
    client = docker.from_env()
    
    try:
        container = client.containers.get(container_id)
        logs = container.logs().decode('utf-8')

        password_match = re.search(r'Auto-generated pass = "(.+?)"', logs)

        if password_match:
            return password_match.group(1)
        else:
            return "No matching password found in the container logs."
    except docker.errors.NotFound:
        return f"Container {container_id} not found."
    except Exception as e:
        return f"Error occurred: {str(e)}"

async def run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp):
    client = docker.from_env()
    container_name = f"openvpn-as{container_suffix}"
    volume_path = f"/etc/openvpn{container_suffix}"

    try:
        container = client.containers.run(
            image="b0721bd08080",  # Replace with actual container image
            name=container_name,
            cap_add=["NET_ADMIN"],
            detach=True,
            ports={
                f'{443}/tcp': port_443,
                f'{943}/tcp': port_943,
                f'{1194}/udp': port_1194_udp
            },
            volumes={
                volume_path: {'bind': '/openvpn', 'mode': 'rw'}
            }
        )
        print(f"Container {container_name} started.")
        return container
    except docker.errors.ContainerError as e:
        print(f"Container error: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Image not found: {e}")
    except docker.errors.APIError as e:
        print(f"Docker API error: {e}")
        
async def delete_container(container_id, user_id):
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        container.stop()
        container.remove()
        print(f"Container {container_id} has been deleted after 20 minutes.")
        # Удаляем пользователя из базы данных
        remove_user(user_id)
    except docker.errors.NotFound:
        print(f"Container {container_id} not found for deletion.")
    except Exception as e:
        print(f"Error deleting container {container_id}: {str(e)}")