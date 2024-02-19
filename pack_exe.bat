REM 本脚本使用 pyinstaller 将 Python 项目打包为 Windows 可执行文件
REM 脚本会添加图标，拷贝预设与配置文件到打包文件夹。
rmdir /s /q dist
pyinstaller --icon=docs\Wechat-AI-Assistant.ico --add-data ".venv\Lib\site-packages\wcferry:wcferry" main.py
rename dist\main\main.exe Wechat-AI-Assistant.exe
robocopy presets dist\main\presets /E
del dist\main\presets\.*.yaml
copy config_template.yaml dist\main\config.yaml
copy config_logging.yaml dist\main\
rename dist\main Wechat-AI-Assistant
explorer.exe dist\Wechat-AI-Assistant