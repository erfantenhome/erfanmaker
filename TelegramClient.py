import random

# A list of possible device parameters to choose from
device_params = [
    {'device_model': 'iPhone 14 Pro Max', 'system_version': '16.5.1', 'app_version': '9.6.3'},
    {'device_model': 'Samsung Galaxy S23 Ultra', 'system_version': 'SDK 33', 'app_version': '9.6.3'},
    {'device_model': 'Google Pixel 7 Pro', 'system_version': 'SDK 33', 'app_version': '9.6.3'},
    {'device_model': 'Desktop', 'system_version': 'Windows 11', 'app_version': '4.8.1'},
]

# Randomly select a set of parameters for the new session
selected_device = random.choice(device_params)

client = TelegramClient(
    session_file,
    api_id,
    api_hash,
    device_model=selected_device['device_model'],
    system_version=selected_device['system_version'],
    app_version=selected_device['app_version']
)
