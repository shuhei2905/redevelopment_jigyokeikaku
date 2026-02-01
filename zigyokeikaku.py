import streamlit as st
import pandas as pd
import sqlite3
import datetime
import altair as alt

# --- データベース設定 ---
DB_NAME = 'biz_plan.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            created_at TIMESTAMP,
            total_area REAL,
            target_far REAL,
            exit_unit_price INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS landowners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            name TEXT,
            area REAL,
            market_price INTEGER,
            offer_price INTEGER,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    conn.commit()
    conn.close()

# --- データベース操作 ---
def save_project(name, total_area, target_far, exit_unit_price, df_landowners):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO projects (name, created_at, total_area, target_far, exit_unit_price)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, datetime.datetime.now(), total_area, target_far, exit_unit_price))
    project_id = c.lastrowid
    
    for _, row in df_landowners.iterrows():
        c.execute('''
            INSERT INTO landowners (project_id, name, area, market_price, offer_price)
            VALUES (?, ?, ?, ?, ?)
        ''', (project_id, row['地権者名'], row['面積'], row['相場価格'], row['提示価格']))
    
    conn.commit()
    conn.close()
    return project_id

def delete_project(project_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM landowners WHERE project_id = ?', (project_id,))
    c.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()

def get_all_projects():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql('SELECT * FROM projects ORDER BY created_at DESC', conn)
    conn.close()
    return df

def get_landowners_by_project(project_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql('SELECT * FROM landowners WHERE project_id = ?', conn, params=(project_id,))
    conn.close()
    return df

# --- インセンティブ計算関数 ---
def calculate_wacc(equity, debt, ke, kd, tax_rate):
    """加重平均資本コスト（rWACC）を計算"""
    total_capital = equity + debt
    if total_capital == 0:
        return 0
    we = equity / total_capital  # 自己資本比率
    wd = debt / total_capital    # 負債比率
    rwacc = (we * ke) + (wd * kd * (1 - tax_rate))
    return rwacc

def calculate_capital_cost(equity, debt, rwacc, months):
    """資本コストを計算"""
    total_capital = equity + debt
    capital_cost = total_capital * rwacc * (months / 12)
    return capital_cost

def get_incentive_rate(grade, is_solo_pm=False):
    """等級に応じたインセンティブ率を返す"""
    rates = {
        "PM S2": 0.08,
        "PM S1": 0.10,
        "PM A1": 0.03,
        "PL B5": 0.07,
        "PL B4": 0.07,
        "PL B3": 0.07,
        "PL B2": 0.07,
    }
    base_rate = rates.get(grade, 0)
    
    # PMが単独で取り纏めた場合、PL率7%を加算
    if is_solo_pm and grade.startswith("PM"):
        base_rate += 0.07
    
    return base_rate

# --- アプリケーション本体 ---
def main():
    st.set_page_config(page_title="事業計画シミュレーター", layout="wide")
    init_db()

    menu = st.sidebar.radio("メニュー", ["シミュレーション実行", "保存データ一覧"])

    if menu == "シミュレーション実行":
        st.title("🏗 事業計画シミュレーター")

        # --- 1. 出口条件設定 ---
        st.subheader("📋 基本条件設定")
        with st.container():
            col_cond1, col_cond2, col_cond3, col_cond4 = st.columns(4)
            if 'target_far' not in st.session_state: st.session_state.target_far = 300.0
            if 'exit_unit_price' not in st.session_state: st.session_state.exit_unit_price = 100
            if 'acquisition_cost_rate' not in st.session_state: st.session_state.acquisition_cost_rate = 5.0

            far = col_cond1.number_input("従後容積(%)", value=st.session_state.target_far, step=10.0)
            exit_unit_price = col_cond2.number_input("出口一種単価(万円)", value=st.session_state.exit_unit_price, step=10)
            acquisition_cost_rate = col_cond3.number_input("物件取得経費（対土地代）(%)", value=st.session_state.acquisition_cost_rate, step=0.5)
            far_ratio = far / 100.0 if far > 0 else 1.0

        st.write("---")

        # --- 2. インセンティブ計算用パラメータ ---
        st.subheader("💰 インセンティブ計算パラメータ")
        
        # 固定値（2025年7月末基準、年1回見直し）
        KE_RATE = 10.0   # 自己資本コスト (%)
        KD_RATE = 2.8    # 負債コスト (%)
        TAX_RATE = 35.0  # 実効税率 (%)
        
        with st.expander("▼ インセンティブ計算条件を設定", expanded=True):
            inc_col1, inc_col2 = st.columns(2)
            
            with inc_col1:
                st.markdown("**📊 資金調達条件**")
                debt_amount = st.number_input(
                    "借入金額（万円）", 
                    value=4000, 
                    step=100,
                    help="融資により調達する金額"
                )
                project_months = st.number_input(
                    "案件期間（月数）", 
                    value=12, 
                    min_value=1, 
                    max_value=60,
                    help="仕入れから売却までの期間"
                )
                
                # 固定パラメータの表示（参考情報）
                st.caption(f"📌 固定パラメータ（2025年7月末基準）")
                st.caption(f"　自己資本コスト(ke): {KE_RATE}% / 負債コスト(kd): {KD_RATE}% / 実効税率: {TAX_RATE}%")
            
            with inc_col2:
                st.markdown("**👤 担当者情報**")
                grade = st.selectbox(
                    "等級",
                    ["PM S2", "PM S1", "PM A1", "PL B5", "PL B4", "PL B3", "PL B2"],
                    index=1,
                    help="取り纏め完了時の等級"
                )
                is_solo_pm = st.checkbox(
                    "PMが単独で取り纏め",
                    value=False,
                    help="PMがピックアップから取り纏めまで単独で行った場合、PL率7%を加算"
                )
                is_third_party_contract = st.checkbox(
                    "第三者のためにする契約",
                    value=False,
                    help="A等級PM・PLの場合、インセンティブ率×1.2"
                )
        
        # 固定値を変数に代入（後続の計算で使用）
        ke_rate = KE_RATE
        kd_rate = KD_RATE
        tax_rate = TAX_RATE

        st.write("---")

        # --- 3. エクセル風編集エリア (Input) ---
        st.subheader("地権者データの入力・編集")
        st.caption("👇 表を直接編集できます。行の追加は一番下の行に入力するか、右上の「＋」を押してください。")

        if 'input_df' not in st.session_state:
            st.session_state.input_df = pd.DataFrame({
                "地権者名": pd.Series(dtype='str'),
                "面積": pd.Series(dtype='float'),
                "相場価格": pd.Series(dtype='int'),
                "提示価格": pd.Series(dtype='int')
            })

        edited_df = st.data_editor(
            st.session_state.input_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "地権者名": st.column_config.TextColumn("地権者名", required=True),
                "面積": st.column_config.NumberColumn("面積 (坪)", format="%.2f", min_value=0.0, default=0.0),
                "相場価格": st.column_config.NumberColumn("相場価格 (万円)", format="%d", min_value=0, default=0),
                "提示価格": st.column_config.NumberColumn("提示価格 (万円)", format="%d", min_value=0, default=0),
            },
            key="main_editor"
        )

        # --- 4. リアルタイム計算処理 ---
        calc_df = edited_df.copy()
        calc_df["面積"] = pd.to_numeric(calc_df["面積"], errors='coerce').fillna(0.0)
        calc_df["相場価格"] = pd.to_numeric(calc_df["相場価格"], errors='coerce').fillna(0)
        calc_df["提示価格"] = pd.to_numeric(calc_df["提示価格"], errors='coerce').fillna(0)

        # 個別計算
        calc_df["差額"] = calc_df["提示価格"] - calc_df["相場価格"]
        calc_df["坪単価"] = calc_df.apply(lambda x: x["提示価格"] / x["面積"] if x["面積"] > 0 else 0, axis=1)
        calc_df["一種単価"] = calc_df.apply(lambda x: x["坪単価"] / far_ratio if far_ratio > 0 else 0, axis=1)

        # 全体集計
        total_area_sum = calc_df["面積"].sum()
        total_offer_sum = calc_df["提示価格"].sum()  # 仕入れ値
        total_market_sum = calc_df["相場価格"].sum()
        
        # 物件取得経費の計算
        acquisition_cost = total_offer_sum * acquisition_cost_rate / 100.0
        
        finish_price = total_offer_sum / total_area_sum / far_ratio if (total_area_sum > 0 and far_ratio > 0) else 0
        exit_gross = total_area_sum * far_ratio * exit_unit_price  # 売値
        profit = exit_gross - total_offer_sum - acquisition_cost  # 案件粗利

        # --- 5. インセンティブ計算 ---
        # 自己資本 = 仕入れ値 - 借入
        equity_amount = total_offer_sum - debt_amount if total_offer_sum > debt_amount else 0
        
        # rWACC計算
        rwacc = calculate_wacc(
            equity=equity_amount,
            debt=debt_amount,
            ke=ke_rate / 100,
            kd=kd_rate / 100,
            tax_rate=tax_rate / 100
        )
        
        # 資本コスト計算
        capital_cost = calculate_capital_cost(
            equity=equity_amount,
            debt=debt_amount,
            rwacc=rwacc,
            months=project_months
        )
        
        # インセンティブ計算対象粗利
        incentive_base_profit = profit - capital_cost
        
        # インセンティブ率取得
        incentive_rate = get_incentive_rate(grade, is_solo_pm)
        
        # 第三者のためにする契約の場合の補正
        if is_third_party_contract:
            if grade == "PM A1" or grade.startswith("PL"):
                incentive_rate *= 1.2
        
        # インセンティブ金額
        incentive_amount = incentive_base_profit * incentive_rate if incentive_base_profit > 0 else 0
        
        profit_margin = profit / exit_gross * 100 if exit_gross > 0 else 0

        # --- 6. 重要指標 (Metrics) ---
        st.markdown("### 📊 シミュレーション結果")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("敷地面積合計", f"{total_area_sum:,.2f} 坪")
        m2.metric("提示価格合計（仕入れ値）", f"{total_offer_sum:,.0f} 万円")
        m3.metric("物件取得経費", f"{acquisition_cost:,.0f} 万円")
        m4.metric("出口グロス（売値）", f"{exit_gross:,.0f} 万円")
        m5.metric("想定利益（案件粗利）", f"{profit:,.0f} 万円", delta=f"{profit:,.0f} 万円" if profit != 0 else None)
        m6.metric("利益率", f"{profit_margin:.2f} %", delta=f"{profit_margin:.2f} %" if profit_margin != 0 else None)

        # --- 7. インセンティブ計算結果 ---
        st.markdown("### 💵 インセンティブ計算結果")
        
        inc_result_col1, inc_result_col2 = st.columns(2)
        
        with inc_result_col1:
            st.markdown("**計算プロセス**")
            
            # 計算過程をテーブルで表示
            calc_process = pd.DataFrame({
                "項目": [
                    "① 案件粗利",
                    "② 自己資本（Equity）",
                    "③ 借入（Debt）",
                    "④ 自己資本比率（we）",
                    "⑤ 負債比率（wd）",
                    "⑥ rWACC",
                    "⑦ 資本コスト",
                    "⑧ インセンティブ対象粗利（①-⑦）",
                ],
                "計算式/値": [
                    f"{profit:,.0f} 万円",
                    f"{equity_amount:,.0f} 万円",
                    f"{debt_amount:,.0f} 万円",
                    f"{equity_amount / (equity_amount + debt_amount) * 100:.1f} %" if (equity_amount + debt_amount) > 0 else "0 %",
                    f"{debt_amount / (equity_amount + debt_amount) * 100:.1f} %" if (equity_amount + debt_amount) > 0 else "0 %",
                    f"{rwacc * 100:.2f} %",
                    f"{capital_cost:,.1f} 万円",
                    f"{incentive_base_profit:,.1f} 万円",
                ]
            })
            st.dataframe(calc_process, hide_index=True, use_container_width=True)
        
        with inc_result_col2:
            st.markdown("**インセンティブ金額**")
            
            # インセンティブ結果
            rate_display = f"{incentive_rate * 100:.1f}%"
            if is_solo_pm and grade.startswith("PM"):
                base_rate = get_incentive_rate(grade, False)
                rate_display = f"{base_rate * 100:.0f}% + 7%（単独取纏め）= {incentive_rate * 100:.0f}%"
            if is_third_party_contract and (grade == "PM A1" or grade.startswith("PL")):
                rate_display += "（×1.2 第三者契約）"
            
            st.info(f"""
            **等級**: {grade}  
            **インセンティブ率**: {rate_display}  
            **対象粗利**: {incentive_base_profit:,.0f} 万円
            """)
            
            if incentive_base_profit > 0:
                st.success(f"### 🎉 インセンティブ: **{incentive_amount:,.0f} 万円**")
            else:
                st.warning("⚠️ 対象粗利がマイナスのため、インセンティブは発生しません")
            
            # 等級別比較
            st.markdown("**等級別インセンティブ比較**")
            grades_comparison = []
            for g in ["PM S2", "PM S1", "PM A1", "PL B5"]:
                rate = get_incentive_rate(g, is_solo_pm if g.startswith("PM") else False)
                if is_third_party_contract and (g == "PM A1" or g.startswith("PL")):
                    rate *= 1.2
                amount = incentive_base_profit * rate if incentive_base_profit > 0 else 0
                grades_comparison.append({
                    "等級": g,
                    "率": f"{rate * 100:.1f}%",
                    "インセンティブ": f"{amount:,.0f} 万円"
                })
            st.dataframe(pd.DataFrame(grades_comparison), hide_index=True, use_container_width=True)

        # --- 8. グラフ描画エリア ---
        if len(calc_df) > 0 and total_area_sum > 0:
            st.write("---")
            st.subheader("📈 視覚的分析")
            
            g_col1, g_col2 = st.columns(2)
            
            with g_col1:
                st.markdown("**💰 相場価格 vs 提示価格**")
                chart_data = calc_df[["地権者名", "相場価格", "提示価格"]].melt("地権者名", var_name="種別", value_name="金額(万円)")
                chart = alt.Chart(chart_data).mark_bar().encode(
                    x=alt.X('地権者名', sort=None, axis=alt.Axis(labelAngle=0)),
                    y='金額(万円)',
                    color=alt.Color('種別', scale=alt.Scale(domain=['相場価格', '提示価格'], range=['#A9A9A9', '#FF6347'])),
                    xOffset='種別',
                    tooltip=['地権者名', '種別', '金額(万円)']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)

            with g_col2:
                st.markdown("**🏗 事業収支の構成**")
                if profit > 0:
                    donut_data = pd.DataFrame({
                        "category": ["原価(取得費)", "物件取得経費", "資本コスト", "想定利益"],
                        "value": [total_offer_sum, acquisition_cost, capital_cost, incentive_base_profit if incentive_base_profit > 0 else 0]
                    })
                    donut_chart = alt.Chart(donut_data).mark_arc(innerRadius=50).encode(
                        theta=alt.Theta(field="value", type="quantitative"),
                        color=alt.Color(field="category", type="nominal", scale=alt.Scale(
                            domain=["原価(取得費)", "物件取得経費", "資本コスト", "想定利益"],
                            range=['#D3D3D3', '#FFB6C1', '#87CEEB', '#32CD32']
                        )),
                        tooltip=["category", "value"]
                    ).properties(height=300)
                    st.altair_chart(donut_chart, use_container_width=True)
                else:
                    st.warning("⚠️ 現在、赤字収支です。")
                    st.bar_chart(pd.DataFrame({"金額": [exit_gross, total_offer_sum]}, index=["出口グロス", "提示価格合計"]))

            # 詳細テーブル
            with st.expander("▼ 計算詳細・内訳を見る", expanded=False):
                st.dataframe(calc_df.style.format({
                    "面積": "{:.2f}",
                    "相場価格": "{:,.0f}",
                    "提示価格": "{:,.0f}",
                    "差額": "{:,.0f}",
                    "坪単価": "{:,.2f}",
                    "一種単価": "{:,.2f}"
                }), use_container_width=True)

        # --- 9. 保存機能 ---
        st.write("---")
        c_save1, c_save2 = st.columns([3, 1])
        save_name = c_save1.text_input("プロジェクト名をつけて保存", placeholder="例：日本橋計画_Ver1")
        if c_save2.button("💾 プロジェクトを保存", type="primary"):
            if save_name and len(calc_df) > 0:
                save_project(save_name, total_area_sum, far, exit_unit_price, calc_df)
                st.success(f"「{save_name}」を保存しました！")
            elif len(calc_df) == 0:
                st.error("地権者データが入力されていません。")
            else:
                st.error("プロジェクト名を入力してください。")

    elif menu == "保存データ一覧":
        st.title("📂 保存済みプロジェクト")
        projects_df = get_all_projects()
        
        if not projects_df.empty:
            for index, project in projects_df.iterrows():
                with st.expander(f"📄 {project['name']} (作成: {project['created_at'][:16]})"):
                    c1, c2 = st.columns([4, 1])
                    landowners_df = get_landowners_by_project(project['id'])
                    
                    with c1:
                        st.caption(f"敷地: {project['total_area']:.2f}坪 | 容積: {project['target_far']}% | 出口一種: {project['exit_unit_price']}万円")
                        st.dataframe(landowners_df[["name", "area", "market_price", "offer_price"]].rename(columns={
                            "name": "地権者名", "area": "面積", "market_price": "相場価格", "offer_price": "提示価格"
                        }), hide_index=True)
                    
                    with c2:
                        if st.button("削除", key=f"del_{project['id']}"):
                            delete_project(project['id'])
                            st.rerun()
                        
                        if st.button("編集再開", key=f"load_{project['id']}"):
                            loaded_data = []
                            for _, l_row in landowners_df.iterrows():
                                loaded_data.append({
                                    "地権者名": l_row['name'],
                                    "面積": l_row['area'],
                                    "相場価格": l_row['market_price'],
                                    "提示価格": l_row['offer_price']
                                })
                            st.session_state.input_df = pd.DataFrame(loaded_data).astype({
                                "地権者名": "str", "面積": "float", "相場価格": "int", "提示価格": "int"
                            })
                            st.session_state.target_far = project['target_far']
                            st.session_state.exit_unit_price = project['exit_unit_price']
                            st.toast("ロードしました。シミュレーション画面へ移動してください", icon="✅")
        else:
            st.write("保存データはありません。")

if __name__ == '__main__':
    main()
