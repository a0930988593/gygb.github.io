#!/usr/bin/env python3
"""台股大盤資金流向：本機即時資料伺服器（只用標準函式庫）。
用法：與 taiwan-market-flow-v2.html 放同一資料夾，執行  python flow_server.py
再開 http://localhost:8000
資料來源：證交所 MIS（mis.twse.com.tw）盤中指數，約 5 秒更新一次。
注意：類股指數代號請自行對照 MIS 網站核對，抓不到的類股會自動略過。
"""
import json, os, re, ssl, threading, time, urllib.request, http.cookiejar, http.server

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'taiwan-market-flow-v2.html')
URL = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp?json=1&delay=0&ex_ch='

# 代號 → 顯示名稱。可自行增減；上櫃代號（o 開頭）需自行核對
TSE = {'t01': '水泥', 't02': '食品', 't03': '塑膠', 't04': '紡織', 't05': '電機', 't06': '電器電纜',
       't21': '化學', 't22': '生技', 't08': '玻璃', 't09': '造紙', 't10': '鋼鐵', 't11': '橡膠',
       't12': '汽車', 't14': '營建', 't15': '航運', 't16': '觀光', 't17': '金融', 't18': '貿易百貨',
       't24': '半導體', 't25': '電腦週邊', 't26': '光電', 't27': '通信網路', 't28': '電零',
       't29': '電子通路', 't30': '資訊服務', 't31': '其他電子'}
OTC = {}  # 上櫃類股：啟動時自動探測 otc_o01~o99 填入（見 discover_otc）

jar = http.cookiejar.CookieJar()
# 證交所憑證缺少 Subject Key Identifier，Python 3.13+ 的嚴格模式會拒絕；
# 這裡只關閉嚴格旗標，其餘憑證驗證（網域、期限、簽發者）照常進行
ctx = ssl.create_default_context()
ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                 urllib.request.HTTPSHandler(context=ctx))
op.addheaders = [('User-Agent', 'Mozilla/5.0'), ('Referer', 'https://mis.twse.com.tw/stock/index.jsp')]
try:  # 先取得 cookie；網址若失效（404）就略過，直接呼叫資料介面
    op.open('https://mis.twse.com.tw/stock/index.jsp', timeout=10)
except Exception as e:
    print('略過 cookie 預取：', e)


def quote(chs):
    u = URL + '|'.join(chs) + '&_=' + str(int(time.time() * 1000))
    return json.load(op.open(u, timeout=10)).get('msgArray', [])


def calc(m):
    try:
        y = float(m['y'])
        z = float(m['z']) if m.get('z') not in (None, '-', '') else y
        return z, z - y, (z - y) / y * 100
    except (KeyError, ValueError, ZeroDivisionError):
        return None


def discover_otc():
    """探測 MIS 的 otc_o01~o99，依回傳的名稱自動建立上櫃類股表"""
    found = {}
    for i in range(1, 100, 33):
        for m in quote(['otc_o%02d.tw' % j for j in range(i, min(i + 33, 100))]):
            code, name = m.get('c', ''), m.get('n', '')
            if not (code.startswith('o') and name and calc(m)) or code == 'o00':
                continue
            if any(k in name for k in ('櫃買', '報酬', '富櫃', '200')):
                continue  # 排除綜合指數與非類股指數
            found[code] = re.sub('櫃檯|類指數|指數', '', name) or name
    return found


def market(ex, main, mname, table):
    out = {'idx': None, 'sec': {}}
    rows = quote(['%s_%s.tw' % (ex, c) for c in [main] + list(table)])
    for m in rows:
        r = calc(m)
        if not r:
            continue
        code = m.get('c', '')
        if code == main:
            out['idx'] = [mname, round(r[0], 2), round(r[1], 2), round(r[2], 2)]
        elif code in table:
            out['sec'][table[code]] = round(r[2], 2)
    return out


def snapshot():
    data = {'time': time.strftime('%H:%M:%S')}
    tse = market('tse', 't00', '加權', TSE)
    if tse['idx'] and tse['sec']:
        data['tse'] = tse
    otc = market('otc', 'o00', '櫃買', OTC) if OTC else None
    if otc and otc['idx'] and otc['sec']:
        data['otc'] = otc
    elif CACHE['otc']:  # 探測不到官方類股指數時，改用個股平均
        oi = market('otc', 'o00', '櫃買', {})['idx']
        if oi:
            data['otc'] = {'idx': oi, 'sec': CACHE['otc']['sec'], 'br': CACHE['otc']['br'], 'note': '個股平均'}
    if 'tse' in data:
        data['tse']['br'] = CACHE['br']
    data['fut'] = CACHE['fut']  # 抓不到時為 None，頁面顯示「無即時資料」
    return data


CACHE = {'br': None, 'otc': None, 'fut': None}
DEBUG = False
TSE_LIST = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'


def count(ex, codes):
    u = d = lu = ld = 0
    for i in range(0, len(codes), 80):
        for m in quote(['%s_%s.tw' % (ex, c) for c in codes[i:i + 80]]):
            try:
                y, z, hi, lo = float(m['y']), float(m['z']), float(m['u']), float(m['w'])
            except (KeyError, ValueError):
                continue  # 尚未成交
            u += z > y
            d += z < y
            lu += z >= hi > y
            ld += z <= lo < y
    return {'u': u, 'd': d, 'lu': lu, 'ld': ld} if u + d else None


def breadth():
    """逐檔查上市股票即時價，統計上漲/下跌/漲停/跌停家數（約 10 次請求）"""
    codes = [r['公司代號'] for r in json.load(op.open(TSE_LIST, timeout=20))
             if len(r.get('公司代號', '')) == 4 and r['公司代號'].isdigit()]
    return count('tse', codes)


OTC_LIST = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O'


def breadth_otc():
    """上櫃：股票清單來自櫃買中心 OpenAPI（欄位名稱未經驗證，失敗則顯示無即時資料）"""
    rows = json.load(op.open(OTC_LIST, timeout=20))
    codes = [c for c in (r.get('SecuritiesCompanyCode') or r.get('公司代號') or '' for r in rows)
             if len(c) == 4 and c.isdigit()]
    return count('otc', codes)


OTC_IND = {'02': '食品工業', '03': '塑膠工業', '04': '紡織纖維', '05': '電機機械', '06': '電器電纜',
           '08': '玻璃陶瓷', '10': '鋼鐵工業', '11': '橡膠工業', '14': '建材營造', '15': '航運業',
           '16': '觀光事業', '17': '金融保險', '18': '貿易百貨', '20': '其他', '21': '化學工業',
           '22': '生技醫療', '23': '油電燃氣', '24': '半導體', '25': '電腦週邊', '26': '光電',
           '27': '通信網路', '28': '電子零組件', '29': '電子通路', '30': '資訊服務', '31': '其他電子',
           '32': '文化創意'}


def otc_pass():
    """上櫃：逐檔查即時價，同時統計漲跌家數，並依產業別算各類股「個股平均漲跌幅」
    （MIS 沒有提供上櫃類股指數，這不是官方指數，數字會與看盤軟體略有差異）"""
    rows = json.load(op.open(OTC_LIST, timeout=20))
    ind = {}
    for r in rows:
        c = r.get('SecuritiesCompanyCode') or r.get('公司代號') or ''
        if len(c) == 4 and c.isdigit():
            ind[c] = str(r.get('SecuritiesIndustryCode') or r.get('產業別') or '').strip()
    if not ind:
        raise ValueError('櫃買股票清單解析失敗，欄位：%s' % (list(rows[0].keys()) if rows else '空'))
    codes = list(ind)
    u = d = lu = ld = 0
    agg = {}
    for i in range(0, len(codes), 80):
        for m in quote(['otc_%s.tw' % c for c in codes[i:i + 80]]):
            try:
                y, z, hi, lo = float(m['y']), float(m['z']), float(m['u']), float(m['w'])
            except (KeyError, ValueError):
                continue  # 尚未成交
            u += z > y
            d += z < y
            lu += z >= hi > y
            ld += z <= lo < y
            name = OTC_IND.get(ind.get(m.get('c', '')))
            if name and y:
                agg.setdefault(name, []).append((z - y) / y * 100)
    sec = {k: round(sum(v) / len(v), 2) for k, v in agg.items() if len(v) >= 2}
    if not sec:
        raise ValueError('沒算出任何上櫃類股；產業別欄位樣本：%s' % list(ind.items())[:5])
    return {'br': {'u': u, 'd': d, 'lu': lu, 'ld': ld} if u + d else None, 'sec': sec}


def one_future(cid):
    body = json.dumps({'MarketType': '0', 'SymbolType': 'F', 'KindID': '1', 'CID': cid,
                       'ExpireMonth': '', 'RowSize': '全部', 'PageNo': '',
                       'SortColumn': '', 'AscDesc': 'A'}).encode()
    req = urllib.request.Request('https://mis.taifex.com.tw/futures/api/getQuoteList', data=body,
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    ql = json.load(op.open(req, timeout=10))['RtData']['QuoteList']
    ids = [x.get('SymbolID', '') for x in ql]
    # 排除價差單（含 /）與現貨指數列（-S），日盤合約（-F）優先，保持近月在前
    cands = sorted([x for x in ql if '/' not in x.get('SymbolID', '') and not x.get('SymbolID', '').endswith('-S')],
                   key=lambda x: not x.get('SymbolID', '').endswith('-F'))
    for q in cands:
        try:
            p, ref = float(q['CLastPrice']), float(q['CRefPrice'])
        except (KeyError, ValueError):
            continue
        df = float(q['CDiff']) if q.get('CDiff') not in (None, '') else p - ref
        if DEBUG:
            print(cid, '代號清單', ids[:8], '→ 採用', q.get('SymbolID'), p)
        return [p, df, round(df / ref * 100, 2)]
    raise ValueError('CID %s 回傳 %d 筆，無可用報價；代號前幾筆：%s' % (cid, len(ql), ids[:6]))


def futures():
    """期交所 MIS：台指、電子、金融期貨近月（商品代號不確定，依序嘗試）"""
    out = []
    for name, cids in (('台指近', ['TXF']), ('電指近', ['EXF', 'TE', 'TEF']), ('金指近', ['FXF', 'TF', 'TFF'])):
        for cid in cids:
            try:
                out.append([name] + one_future(cid))
                break
            except Exception as e:
                print('期貨', name, cid, '失敗：', repr(e))
    return out or None


def refresher():
    while True:
        for key, fn in (('br', breadth), ('otc', otc_pass), ('fut', futures)):
            try:
                CACHE[key] = fn()
            except Exception as e:
                print(key, '更新失敗：', e)
        time.sleep(15)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/market'):
            try:
                body, ctype = json.dumps(snapshot()).encode(), 'application/json'
            except Exception as e:
                self.send_error(502, str(e))
                return
        else:
            body, ctype = open(PAGE, 'rb').read(), 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':  # python flow_server.py test
        for ch in ['tse_t00.tw', 'tse_t01.tw', 'otc_o00.tw']:
            try:
                print(ch, '→', json.dumps(quote([ch]), ensure_ascii=False)[:400])
            except Exception as e:
                print(ch, '失敗：', e)
        DEBUG = True
        print('期貨 →', futures())
        print('漲跌家數 →', breadth())
        try:
            OTC.update(discover_otc())
            print('上櫃類股（%d 類）→' % len(OTC), OTC)
        except Exception as e:
            print('上櫃類股探測失敗：', repr(e))
        try:
            r = otc_pass()
            print('上櫃漲跌家數 →', r['br'])
            print('上櫃類股（%d 類，個股平均）→' % len(r['sec']), r['sec'])
        except Exception as e:
            print('上櫃個股統計失敗：', repr(e))
        sys.exit()
    try:
        OTC.update(discover_otc())
        print('上櫃類股 %d 類：%s' % (len(OTC), '、'.join(OTC.values())))
    except Exception as e:
        print('上櫃類股探測失敗：', repr(e))
    threading.Thread(target=refresher, daemon=True).start()
    print('http://localhost:8000（漲跌家數與期貨約 15 秒更新一次，剛啟動時會先顯示「無即時資料」）')
    http.server.ThreadingHTTPServer(('0.0.0.0', 8000), H).serve_forever()
