# 九巴到站（Home Assistant）

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lopowa&repository=ha-kmb-eta&category=integration)

撳上面個掣，會打開你部 Home Assistant，喺 HACS 加呢個 repo。要先裝好 [HACS](https://hacs.xyz/)。加完之後去 **HACS → 整合 → 九巴到站 → 下載**，重啟，然後 **設定 → 裝置與服務 → 新增整合 → 九巴到站**。

後台可以搜尋站名，再一次揀多條路線。每條路線一個 sensor，狀態係下一班仲有幾多分鐘。跟住三班時間放喺 attributes。

資料來源：運輸署轉發嘅九巴／龍運開放數據，唔使 API key。大約每 60 秒更新一次。

## 手動安裝

1. 將 `custom_components/kmb_eta` 放到 `/config/custom_components/kmb_eta/`。
2. 重啟 Home Assistant。
3. **設定 → 裝置與服務 → 新增整合 → 九巴到站**。

## 用法

1. 輸入站名（例如 `美孚`）。如果出多過一個站，揀正確嗰條站柱。
2. 剔選想睇嘅路線（可多條）。
3. 同一個站要改路線：打開整合 → **配置**。第二個站就再新增一次整合。

## Sensor

| 項目 | 內容 |
| --- | --- |
| 狀態 | 下一班仲有幾多分鐘。冇班次係 `unknown` |
| `eta_1` `eta_2` `eta_3` | 頭三班時間，例如 `18:40` |
| `destination` | 目的地 |
| `remark` | 備註，例如「原定班次」 |
| `mins_2` `mins_3` | 第二、第三班仲有幾多分鐘 |

## 限制

路線清單係靠該站而家嘅 ETA 回應。收咗車嘅線新增嗰陣未必出現，有班次之後再開「配置」就可以揀到。
