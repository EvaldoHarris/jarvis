import unittest
from pathlib import Path
from playwright.async_api import async_playwright


class TaskPanelBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_mobile_progress_and_authenticated_pause(self):
        static=Path(__file__).parent/'static'
        plan={'id':'fixture','revision':1,'state':'active','objective':'Comecar meu trabalho','completed':1,'total':3,'reason':'',
              'steps':[{'title':'Abrir Discord','state':'done'},{'title':'Abrir VS Code','state':'pending'},{'title':'Abrir Chrome','state':'pending'}]}
        calls=[]
        async with async_playwright() as playwright:
            browser=await playwright.chromium.launch(headless=True,channel='msedge')
            page=await browser.new_page(viewport={'width':390,'height':844},is_mobile=True)
            await page.add_init_script("try { sessionStorage.setItem('jarvis_token','fixture-token'); } catch {}")
            await page.route_web_socket('**/ws?*',lambda ws:None)
            async def handle(route):
                request=route.request
                path=request.url.split('8769')[-1]
                if path=='/api/panel':return await route.fulfill(json={'name':'JARVIS','connected':True,'state':'THINKING','hud_style':'core','muted':True,'cpu':12,'memory':40})
                if path=='/api/tasks':
                    if request.method=='POST':
                        calls.append((request.headers,request.post_data_json))
                        plan['state']='paused';plan['revision']=2
                    return await route.fulfill(json={'plan':plan})
                if path.startswith('/assets/'):return await route.fulfill(content_type='application/javascript' if path.endswith('.js') else 'text/css',body=(static/path.split('/')[-1]).read_text(encoding='utf-8'))
                if path=='/':return await route.fulfill(content_type='text/html',body=(static/'app.html').read_text(encoding='utf-8'))
                return await route.fulfill(status=404)
            await page.route('**/*',handle)
            await page.goto('http://127.0.0.1:8769/',wait_until='domcontentloaded')
            await page.locator('#task-title').filter(has_text='Em andamento').wait_for(timeout=5000)
            await page.get_by_role('button',name='Pausar',exact=True).click()
            await page.locator('#task-title').filter(has_text='Pausada').wait_for(timeout=5000)
            self.assertEqual(calls[0][0]['authorization'],'Bearer fixture-token')
            self.assertEqual(calls[0][1],{'action':'pause','plan_id':'fixture','revision':1})
            output=static.parents[1]/'logs'
            output.mkdir(exist_ok=True)
            await page.screenshot(path=str(output/'qa-web-task-panel-050.png'))
            await browser.close()


if __name__=='__main__':unittest.main()
