import docker,requests
from requests.auth import HTTPBasicAuth
import re
import asyncio
from tqdm.asyncio import tqdm as async_tqdm

async def create_openvpn_config(container_id):
    """
    Генерация OpenVPN конфигурации для указанного контейнера.
    """
    client = docker.from_env()

    # Получаем информацию о контейнере по его ID
    container = client.containers.get(container_id)

    # Извлекаем порты контейнера
    container_ports = container.attrs['NetworkSettings']['Ports']
    internal_port_tcp = f"{443}/tcp"
    connect_port_tcp = container_ports.get(internal_port_tcp, [])
    connect_port_tcp_value = connect_port_tcp[0]['HostPort'] if connect_port_tcp else None

    if not connect_port_tcp_value:
        raise ValueError(f"Container {container_id} does not have a mapped TCP port.")

    # URL для обращения к API контейнера
    url = f'https://localhost:{connect_port_tcp_value}/rest/GetGeneric'
    print(f"URL for container {container_id}: {url}")

    # Дефолтное имя пользователя OpenVPN
    username = 'openvpn'

    # Получаем пароль из логов контейнера
    password = await parse_container_logs_for_password(container_id)
    print("password:", password)
    if not password:
        raise ValueError("Failed to extract password from container logs.")

    try:
        # Выполняем запрос к API контейнера
        response = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
        response.raise_for_status()  # Проверка успешного статуса
        payload = response.content.decode('utf-8')
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to fetch OpenVPN config from {url}: {e}")

    # Внутренний IP контейнера
    internal_ip = container.attrs['NetworkSettings']['IPAddress']

    # Заменяем внутренний IP контейнера на внешний IP сервера
    external_ip = "109.120.179.155"  # Укажите ваш внешний IP
    modified_payload = payload.replace(internal_ip, external_ip)
    
    # Подставляем внешний порт
    modified_payload = modified_payload.replace('443', str(connect_port_tcp_value))

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
{username}
{password}
</auth-user-pass>
"""

    # Формируем финальную конфигурацию
    final_payload = cleaned_payload + "\n" + auth_user_pass.strip()

    # Кодируем строку в байты для отправки как файл
    encoded_payload = final_payload.encode('utf-8')

    return encoded_payload
async def wait_with_progress_bar(max_retries=10, delay=5):
    """
    Прогресс-бар ожидания.
    
    :param max_retries: Максимальное количество шагов ожидания.
    :param delay: Задержка между шагами (в секундах).
    """
    async for _ in async_tqdm(range(max_retries), desc="Ожидание запуска контейнера"):
        await asyncio.sleep(delay)

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


async def parse_container_logs_for_password(container_id):
    """
    Асинхронно извлекает автоматически сгенерированный пароль из логов контейнера.
    """
    client = docker.from_env()

    def get_logs():
        try:
            container = client.containers.get(container_id)
            logs = container.logs().decode('utf-8')
            return logs
        except docker.errors.NotFound:
            return f"Container {container_id} not found."
        except Exception as e:
            return f"Error occurred: {str(e)}"

    logs = await asyncio.get_event_loop().run_in_executor(None, get_logs)
    print("Container Logs:")
    print(logs)

    if "Error occurred" in logs or "Container not found" in logs:
        return logs

    password_match = re.search(r'Auto-generated pass = "(.+?)"', logs)
    if password_match:
        return password_match.group(1)
    else:
        return "No matching password found in the container logs."


async def run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp):
    client = docker.from_env()
    container_name = f"openvpn-as{container_suffix}"
    volume_path = f"/etc/openvpn{container_suffix}"

    try:
        container = client.containers.run(
            image="openvpn/openvpn-as",
            name=container_name,
            cap_add=["NET_ADMIN"],
            devices=["/dev/net/tun"],
            privileged=True,
            detach=True,
            ports={
                f'{443}/tcp': port_443,
                f'{943}/tcp': port_943,
                f'{1194}/udp': port_1194_udp
            },
            volumes={
                volume_path: {'bind': '/etc/openvpn', 'mode': 'rw'}
            }
        )
        print(f"Container {container_name} started.")

        # Проверка готовности контейнера
        await wait_for_container_ready(container)

        return container
    except docker.errors.ContainerError as e:
        print(f"Container error: {e}")
        return None
    except docker.errors.ImageNotFound as e:
        print(f"Image not found: {e}")
        return None
    except docker.errors.APIError as e:
        print(f"Docker API error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


async def wait_for_container_ready(container, max_retries=10, delay=5):
    """
    Ожидает, пока контейнер будет готов, проверяя его состояние.
    
    :param container: Объект контейнера Docker.
    :param max_retries: Максимальное количество проверок.
    :param delay: Задержка между проверками (в секундах).
    """
    client = docker.from_env()
    
    for attempt in range(max_retries):
        try:
            container.reload()  # Обновляем данные контейнера
            logs = container.logs().decode('utf-8')
            
            # Проверяем наличие строк, указывающих на готовность контейнера
            if "Initialization Sequence Completed" in logs:
                print("Container is ready.")
                return True
            
            print(f"Waiting for container to be ready... Attempt {attempt + 1}/{max_retries}")
        except Exception as e:
            print(f"Error checking container readiness: {e}")
        
        await asyncio.sleep(delay)

    print(f"Container is not ready after {max_retries} retries.")
    return False
