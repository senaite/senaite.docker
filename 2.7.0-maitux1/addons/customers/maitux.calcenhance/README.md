# MedAi Calculation Enhancement for  LIMS

涓? LIMS 鐨勮绠楀叕寮忥紙Calculation锛夋ā鍧楀鍔犱袱绉嶆柊鐨?Interim Field 鎺т欢绫诲瀷锛屾敮鎸?HPLC 鍚噺娴嬪畾绛夊鏉傝绠楀満鏅€?
**鐗堟湰锛?* 1.0.0  
**鍏煎锛?*  2.x

---

## 鏂板鍔熻兘

### 1. List (array) 鈥?鍒楄〃杈撳叆

鍏佽鐢ㄦ埛杈撳叆澶氫釜骞跺垪鍊硷紙濡傚閽堣繘鏍风殑宄伴潰绉級锛岀郴缁熻嚜鍔ㄨ绠楀钩鍧囧€煎苟瀛樺偍銆?
- 褰曞叆鏃跺嚭鐜板涓緭鍏ユ锛岄€氳繃 **+/-** 鎸夐挳澧炲垹
- 淇濆瓨鏃惰嚜鍔ㄨ绠楁墍鏈夋湁鏁堟暟鍊肩殑**绠楁湳骞冲潎鍊?*

### 2. Calculated 鈥?瀛愬叕寮忚嚜鍔ㄨ绠?
鍙瀛楁锛屽€肩敱 Inter-Interim 瀛愬叕寮忚嚜鍔ㄨ绠楀緱鍑恒€傛敮鎸侀€氳繃 `[keyword]` 寮曠敤鍏朵粬 Interim Field锛屽紩鎿庤嚜鍔ㄨВ鏋愪緷璧栧叧绯诲苟鎸夋嫇鎵戦『搴忔眰鍊笺€?
- 鍦?Interim Fields 琛ㄦ牸涓紝**Control type** 閫夋嫨 `Calculated`锛屽湪鏂板鐨?**Formula** 鍒椾腑濉啓瀛愬叕寮?- 瀛愬叕寮忚娉曪細`([Keyword1] * [Keyword2]) / [Keyword3]`
- 鏀寔鏍囧噯鏁板鍑芥暟锛歚abs`, `max`, `min`, `round`, `sum`, `pow`, `sqrt`, `log`, `log10`, `exp`, `floor`, `ceil`

---

## 瀹夎鏂规硶

### 1. 鍑嗗鏂囦欢

灏?`maitux.calcenhance` 鐩綍鏀惧湪  婧愮爜鐩綍涓嬶紙涓?`senaite.core` 鍚岀骇锛夛細

```
/home/senaite/senaitelims/src/maitux.calcenhance/
```

### 2. 娉ㄥ唽 Add-on

鍦? 瀹炰緥鐨?ZCML 閰嶇疆涓坊鍔狅紙閫氬父鍦?`package-includes/` 鐩綍涓嬪垱寤?`.zcml` 鏂囦欢锛夛細

```xml
<include package="maitux.calcenhance" />
```

纭繚 `maitux.calcenhance` 鍦?Python 璺緞涓紙鍙€氳繃 `develop-eggs` 鎴?`egg-link` 鏂瑰紡锛夈€?
### 3. 閲嶅惎 Zope 瀹炰緥

```bash
# Docker 鐜
docker compose restart senaite

# 鏅€氱幆澧?bin/instance restart
```

### 4. 楠岃瘉瀹夎

閲嶅惎鍚庤闂? 鍚庡彴锛岃繘鍏?**Setup 鈫?Calculations**锛岀紪杈戜换鎰?Calculation锛屽湪 Interim Fields 琛ㄦ牸涓細

- **Control type** 涓嬫媺妗嗗簲鍑虹幇 `List (array)` 鍜?`Calculated` 閫夐」
- 琛ㄦ牸鏈€鍙充晶搴斿嚭鐜?**Formula** 鍒?
---

## 鍔熻兘浣跨敤璇存槑

### List (array) 绫诲瀷

鍦?Calculation 鐨?Interim Fields 涓坊鍔犱竴涓瓧娈碉細

| 瀛楁 | 鍊?|
|------|-----|
| Keyword | `Std1PeakArea` |
| Field Title | 瀵圭収鍝?宄伴潰绉?|
| Control type | List (array) |

鍦?Worksheet 鎴?Analysis 椤甸潰褰曞叆缁撴灉鏃讹紝璇ュ瓧娈典細鏄剧ず澶氫釜杈撳叆妗嗭紝鍙互杈撳叆澶氶拡杩涙牱鐨勫嘲闈㈢Н鍊硷紙濡?102345, 103210, 101980锛夈€備繚瀛樺悗锛岀郴缁熻嚜鍔ㄨ绠楀钩鍧囧€煎瓨鍌ㄣ€?
### Calculated 绫诲瀷

鍦?Calculation 鐨?Interim Fields 涓坊鍔犱竴涓瓧娈碉細

| 瀛楁 | 鍊?|
|------|-----|
| Keyword | `DilutionFactor` |
| Field Title | 绋€閲婂洜瀛?|
| Control type | Calculated |
| Formula | `(200 * 1) / (10 * 1000)` |

鎴栧湪 Formula 涓娇鐢?`[keyword]` 寮曠敤鍏朵粬瀛楁锛?
| 瀛楁 | 鍊?|
|------|-----|
| Keyword | `RF` |
| Field Title | 鍝嶅簲鍥犲瓙 |
| Control type | Calculated |
| Formula | `([AvgPeakArea] * [Volume]) / ([Weight] * [Purity])` |

---

## 绀轰緥锛欻PLC 鍚噺娴嬪畾瀹屾暣閰嶇疆

浠?**S1905 鍘熸枡鑽惈閲忔祴瀹?* 涓轰緥锛屽疄鐜颁粠鍘熷鏁版嵁鍒版渶缁堝惈閲忕殑鑷姩鍖栬绠椼€?
### 涓氬姟鑳屾櫙

- 瀵圭収鍝佹憾娑查厤鍒?2 浠斤紝渚涜瘯鍝佹憾娑查厤鍒?2 浠?- 瀵圭収鍝?杩涙牱 6 閽堬紝瀵圭収鍝?杩涙牱 2 閽?- 姣忎唤渚涜瘯鍝佽繘鏍?2 閽?- 鍏堣绠楀搷搴斿洜瀛?RF锛屽啀璁＄畻鍚噺锛屾渶鍚庤绠楁棤姘寸墿鍚噺

### Step 1锛氬垱寤?Calculation 鍏紡

鍦? 涓繘鍏?**Setup 鈫?Calculations 鈫?Add**锛屽垱寤哄悕涓?鍚噺娴嬪畾-S1905"鐨勮绠楀叕寮忋€?
**涓诲叕寮忥紙Calculation Formula锛夛細**

```
([Content1] + [Content2]) / 2
```

璇ュ叕寮忚绠椾袱浠戒緵璇曞搧婧舵恫鐨勫钩鍧囧惈閲忋€俙Content1` 鍜?`Content2` 鏄笅闈㈠畾涔夌殑 Calculated 绫诲瀷 Interim Field銆?
### Step 2锛氶厤缃?Interim Fields

鎸変互涓嬮『搴忔坊鍔?Interim Fields锛?
#### 鎵嬪伐杈撳叆瀛楁

**瀵圭収鍝?鐩稿叧淇℃伅锛?*

| # | Keyword | Field Title | Control type | Default value | Formula |
|---|---------|-------------|-------------|---------------|---------|
| 1 | Weight1 | 瀵圭収鍝?绉版牱閲?mg) | Numeric | | |
| 2 | Volume1 | 瀵圭収鍝?绋€閲婁綋绉?ml) | Numeric | 200 | |
| 3 | Purity1 | 瀵圭収鍝?鍚噺(%) | Numeric | 99.5 | |
| 4 | Std1PeakArea | 瀵圭収鍝?宄伴潰绉?6閽? | **List (array)** | | |

**瀵圭収鍝?鐩稿叧淇℃伅锛?*

| # | Keyword | Field Title | Control type | Default value | Formula |
|---|---------|-------------|-------------|---------------|---------|
| 5 | Weight2 | 瀵圭収鍝?绉版牱閲?mg) | Numeric | | |
| 6 | Volume2 | 瀵圭収鍝?绋€閲婁綋绉?ml) | Numeric | 200 | |
| 7 | Purity2 | 瀵圭収鍝?鍚噺(%) | Numeric | 99.5 | |
| 8 | Std2PeakArea | 瀵圭収鍝?宄伴潰绉?2閽? | **List (array)** | | |

**渚涜瘯鍝佺浉鍏充俊鎭細**

| # | Keyword | Field Title | Control type | Default value | Formula |
|---|---------|-------------|-------------|---------------|---------|
| 9 | SampleWeight1 | 渚涜瘯鍝?绉版牱閲?mg) | Numeric | | |
| 10 | SampleVolume1 | 渚涜瘯鍝?绋€閲婁綋绉?ml) | Numeric | 200 | |
| 11 | Sample1PeakArea | 渚涜瘯鍝?宄伴潰绉?2閽? | **List (array)** | | |
| 12 | SampleWeight2 | 渚涜瘯鍝?绉版牱閲?mg) | Numeric | | |
| 13 | SampleVolume2 | 渚涜瘯鍝?绋€閲婁綋绉?ml) | Numeric | 200 | |
| 14 | Sample2PeakArea | 渚涜瘯鍝?宄伴潰绉?2閽? | **List (array)** | | |

**姘村垎锛?*

| # | Keyword | Field Title | Control type | Default value | Formula |
|---|---------|-------------|-------------|---------------|---------|
| 15 | KF | 姘村垎(%) | Numeric | 0 | |

#### 鑷姩璁＄畻瀛楁锛圕alculated锛?
**鍝嶅簲鍥犲瓙锛?*

| # | Keyword | Field Title | Control type | Formula |
|---|---------|-------------|-------------|---------|
| 16 | RF1 | 鍝嶅簲鍥犲瓙-瀵圭収鍝? | **Calculated** | `([Std1PeakArea] / [Weight1]) * ([Volume1] / [Purity1])` |
| 17 | RF2 | 鍝嶅簲鍥犲瓙-瀵圭収鍝? | **Calculated** | `([Std2PeakArea] / [Weight2]) * ([Volume2] / [Purity2])` |
| 18 | RF_avg | 骞冲潎鍝嶅簲鍥犲瓙 | **Calculated** | `([RF1] + [RF2]) / 2` |

> **鍏紡璇存槑锛堝鐓у惈閲忔柟娉?Section 7.1锛夛細**
> RF = A_STD 脳 V_STD / (W_STD 脳 P_STD)
> = (A_STD / W_STD) 脳 (V_STD / P_STD)

**鍚噺璁＄畻锛?*

| # | Keyword | Field Title | Control type | Formula |
|---|---------|-------------|-------------|---------|
| 19 | Content1 | 鍚噺-渚涜瘯鍝? | **Calculated** | `([Sample1PeakArea] * [SampleVolume1]) / ([SampleWeight1] * [RF_avg])` |
| 20 | Content2 | 鍚噺-渚涜瘯鍝? | **Calculated** | `([Sample2PeakArea] * [SampleVolume2]) / ([SampleWeight2] * [RF_avg])` |

> **鍏紡璇存槑锛堝鐓у惈閲忔柟娉?Section 7.2锛夛細**
> 鍚噺 = A_SPL 脳 V_SPL / (W_SPL 脳 RF)

### Step 3锛氫緷璧栭『搴忚鏄?
Calculated 寮曟搸浼氳嚜鍔ㄨ繘琛屾嫇鎵戞帓搴忥紝姹傚€奸『搴忎负锛?
1. 鎵嬪伐杈撳叆鐨?Numeric/List 瀛楁 鈫?鐢ㄦ埛濉啓鍚庤幏寰楀€?2. `RF1` 鈫?渚濊禆 `Std1PeakArea`, `Weight1`, `Volume1`, `Purity1`
3. `RF2` 鈫?渚濊禆 `Std2PeakArea`, `Weight2`, `Volume2`, `Purity2`
4. `RF_avg` 鈫?渚濊禆 `RF1`, `RF2`
5. `Content1` 鈫?渚濊禆 `Sample1PeakArea`, `SampleVolume1`, `SampleWeight1`, `RF_avg`
6. `Content2` 鈫?渚濊禆 `Sample2PeakArea`, `SampleVolume2`, `SampleWeight2`, `RF_avg`

涓诲叕寮?`([Content1] + [Content2]) / 2` 鍦ㄦ墍鏈?Calculated 瀛楁璁＄畻瀹屾垚鍚庢眰鍊硷紝杈撳嚭鏈€缁堢粨鏋溿€?
### Step 4锛氭搷浣滄祦绋?
1. 鍦?Analysis Service 涓叧鑱旀 Calculation
2. 鍦?Worksheet 涓綍鍏ユ暟鎹細
   - 閫夋嫨 `Std1PeakArea` 鈫?寮瑰嚭 2 涓緭鍏ユ锛堥粯璁わ級锛岀偣鍑?**+** 澧炲姞鍒?6 涓紝杈撳叆 6 閽堝嘲闈㈢Н
   - 閫夋嫨 `Std2PeakArea` 鈫?杈撳叆 2 涓€?   - 閫夋嫨 `Sample1PeakArea` 鈫?杈撳叆 2 涓€?   - 閫夋嫨 `Sample2PeakArea` 鈫?杈撳叆 2 涓€?   - `Weight1`, `Weight2`, `SampleWeight1`, `SampleWeight2` 鈫?杈撳叆绉版牱閲?   - `KF` 鈫?杈撳叆姘村垎鍊?3. 姣忔淇濆瓨浠绘剰 Interim 鍊煎悗锛岀郴缁熻嚜鍔ㄩ噸鏂拌绠楁墍鏈?Calculated 瀛楁
4. 鎻愪氦缁撴灉鏃讹紝涓诲叕寮忚绠椾袱浠戒緵璇曞搧鐨勫钩鍧囧惈閲?
---

## 瀛愬叕寮忚娉曞弬鑰?
### 鍩烘湰璇硶

```
([Keyword1] + [Keyword2]) / [Keyword3]
```

- 鐢?`[keyword]` 寮曠敤鍏朵粬 Interim Field 鐨?keyword
- 鏀寔鍩烘湰杩愮畻绗︼細`+ - * / ( )`
- 鏀寔骞傝繍绠楋細`[A] ^ 2` 鎴?`pow([A], 2)`

### 鍙敤鍑芥暟

| 鍑芥暟 | 璇存槑 | 绀轰緥 |
|------|------|------|
| `abs(x)` | 缁濆鍊?| `abs([A])` |
| `max(a,b,...)` | 鏈€澶у€?| `max([A], [B])` |
| `min(a,b,...)` | 鏈€灏忓€?| `min([A], 0)` |
| `round(x,n)` | 鍥涜垗浜斿叆 | `round([A], 4)` |
| `sum(...)` | 姹傚拰 | 鈥?|
| `pow(x,y)` | x鐨剏娆℃柟 | `pow([A], 2)` |
| `sqrt(x)` | 骞虫柟鏍?| `sqrt([A])` |
| `log(x)` | 鑷劧瀵规暟 | `log([A])` |
| `log10(x)` | 甯哥敤瀵规暟 | `log10([A])` |
| `exp(x)` | e鐨剎娆℃柟 | `exp([A])` |
| `floor(x)` | 鍚戜笅鍙栨暣 | `floor([A])` |
| `ceil(x)` | 鍚戜笂鍙栨暣 | `ceil([A])` |

### List 绫诲瀷鍊肩殑寮曠敤

鍦?Calculated 瀛愬叕寮忎腑寮曠敤 List 绫诲瀷鐨勫瓧娈垫椂锛屼娇鐢ㄧ殑鏄?*绯荤粺鑷姩璁＄畻鐨勫钩鍧囧€?*锛堟墍鏈夊閽堟暟鎹殑绠楁湳骞冲潎锛夛紝鏃犻渶鎵嬪姩澶勭悊澶氬€笺€?
---

## 鏂囦欢缁撴瀯

```
maitux.calcenhance/
鈹溾攢鈹€ README.md                          # 鏈枃妗?鈹溾攢鈹€ setup.py                           # Python 鍖呴厤缃?鈹斺攢鈹€ src/
    鈹斺攢鈹€ maitux/
        鈹溾攢鈹€ __init__.py                # namespace package
        鈹斺攢鈹€ calcenhance/
            鈹溾攢鈹€ __init__.py            # 鍏ュ彛锛氳皟鐢?apply_patches()
            鈹溾攢鈹€ configure.zcml         # 涓?ZCML 閰嶇疆
            鈹溾攢鈹€ overrides.zcml         # 瑕嗙洊鏍稿績 vocabulary 鐨?ZCML
            鈹溾攢鈹€ patches.py             # 鎵€鏈?monkey-patch 閫昏緫
            鈹溾攢鈹€ config/
            鈹?  鈹溾攢鈹€ __init__.py
            鈹?  鈹斺攢鈹€ vocabularies.py    # ADDITIONAL_RESULT_TYPES 瀹氫箟
            鈹溾攢鈹€ profiles/
            鈹?  鈹溾攢鈹€ __init__.py
            鈹?  鈹溾攢鈹€ configure.zcml     # GenericSetup 娉ㄥ唽
            鈹?  鈹溾攢鈹€ default/
            鈹?  鈹?  鈹斺攢鈹€ metadata.xml
            鈹?  鈹斺攢鈹€ uninstall/
            鈹?      鈹斺攢鈹€ metadata.xml
            鈹斺攢鈹€ vocabularies/
                鈹溾攢鈹€ __init__.py
                鈹溾攢鈹€ configure.zcml     # vocabulary 瑕嗙洊娉ㄥ唽
                鈹斺攢鈹€ resulttypes.py     # ResultTypesVocabulary 瑕嗙洊
```

---

## 娉ㄦ剰浜嬮」

1. **Formula 鍒楀叏灞€鍙**锛欶ormula 鍒楀湪鎵€鏈?Interim Fields 琛ㄦ牸涓潎鏄剧ず锛屼絾浠呭綋 Control type 閫夋嫨 `Calculated` 鏃舵墠鏈夊疄闄呬綔鐢?2. **寰幆渚濊禆澶勭悊**锛氬鏋?Calculated 瀛楁涔嬮棿瀛樺湪寰幆渚濊禆锛屽紩鎿庝細鎸夊畾涔夐『搴忔眰鍊硷紙涓嶄繚璇佹纭€э紝璇烽伩鍏嶅惊鐜紩鐢級
3. **鍏紡閿欒瀹归敊**锛氬瓙鍏紡姹傚€煎け璐ユ椂锛岃 Calculated 瀛楁淇濈暀鍘熷€间笉鍙橈紝涓嶄細闃绘柇淇濆瓨娴佺▼
4. **List 绫诲瀷鏁版嵁鏍煎紡**锛氭瘡娆′慨鏀?List 绫诲瀷瀛楁鍚庯紝绯荤粺鑷姩閲嶆柊璁＄畻骞冲潎鍊煎苟瑕嗙洊瀛樺偍鐨勫€?
