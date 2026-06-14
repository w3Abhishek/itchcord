# itchcord.spec
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[
        'pypresence',
        'pystray',
        'websockets',
        'psutil',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'asyncio',
        'tkinter',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='itchcord',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/tray_icon.png',
)
