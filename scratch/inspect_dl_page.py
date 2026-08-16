import httpx
import asyncio

async def inspect_dl_html():
    url = "https://gamerxyt.com/dl.php?link=https://video-downloads.googleusercontent.com/ADGPM2micSXWAFGvwavGPfnBx3MtSv1JDFIs3fKRN4y1dQCoiytss_aS9gia_t_yGQbR-8yYnAhgUpfpIcuWSaADYBRNcoLUMFi3KPyUj5jXGQ9e3nszZgJTsKE2VuGufV2Nl4Yhk6Phy6wH61-BOrnSQ4xuBQNLT_0V3O5nVaMV0kzpSQwJgKGIqf6xTibvGwDFp4A4u5bGQkbkBTihDYCFbG_pFXFaKEbaLyiTbX8KkCwPv8Gk-s_A6A8pCUK0MM0OHbYvDAcz"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://gamerxyt.com/'
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)
        with open("scratch/dl_page.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("Saved scratch/dl_page.html, size:", len(resp.text))

if __name__ == '__main__':
    asyncio.run(inspect_dl_html())
