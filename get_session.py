import asyncio

# Fix Pyrogram event loop crash on Python 3.12/3.14
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client

async def main():
    try:
        api_id = int(input('Nhập API ID: ').strip())
        api_hash = input('Nhập API HASH: ').strip()
        
        print("\nKhởi tạo Client...")
        async with Client('temp_session', api_id=api_id, api_hash=api_hash) as app:
            session_string = await app.export_session_string()
            print('\n' + '='*50)
            print('USER_SESSION_STRING của bạn là:\n')
            print(session_string)
            print('='*50)
            print('\nHãy copy toàn bộ đoạn chuỗi trên và dán vào file .env.')
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
