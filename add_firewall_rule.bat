@echo off
echo =======================================================
echo   MO CONG 7071 TRON TUONG LUA WINDOWS FIREWALL
echo =======================================================
echo.
netsh advfirewall firewall add rule name="Stremio Addon 7071" dir=in action=allow protocol=TCP localport=7071
echo.
if %errorlevel% equ 0 (
    echo [OK] DA MO CONG 7071 THANH CONG!
    echo Bay gio ban co the ket noi qua IP LAN: http://192.168.88.37:7071
) else (
    echo [LOI] CHUA MO DUOC TUONG LUA.
    echo Ban can nhap chuot phai vao file add_firewall_rule.bat va chon "Run as administrator".
)
echo.
pause
