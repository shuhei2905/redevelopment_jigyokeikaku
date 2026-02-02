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
        ''', (project_id, row['地権者名'], row['面積(坪)'], row['相場金額(坪)'], row['提案金額(坪)']))

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
    """加重平均資本コスト(rWACC)を計算"""
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
            col_cond1, col_cond2 = st.columns(2)
            if 'target_far' not in st.session_state: st.session_state.target_far = 300.0
            if 'exit_unit_price' not in st.session_state: st.session_state.exit_unit_price = 100
            far = col_cond1.number_input("従後容積(%)", value=st.session_state.target_far, step=10.0)
            exit_unit_price = col_cond2.number_input("出口一種単価(万円)", value=st.session_state.exit_unit_price, step=10)
            far_ratio = far / 100.0 if far > 0 else 1.0
        st.write("---")

        # --- 1.5 諸経費・販管費設定 ---
        st.subheader("📝 経費設定")

        cost_col1, cost_col2 = st.columns(2)

        with cost_col1:
            st.markdown("**諸経費(粗利Ⅰ計算用)**")
            acquisition_cost_rate = st.number_input(
                "物件取得経費(対土地代)(%)",
                value=5.0,
                step=0.5,
                help="登記費用、不動産取得税など"
            )

            # 動的に経費を追加できるエディタ
            st.caption("👇 その他経費(＋ボタンで追加)")
            if 'expense_df' not in st.session_state:
                st.session_state.expense_df = pd.DataFrame({
                    "経費名": ["測量費用", "即決和解費用"],
                    "金額(万円)": [0, 0]
                })

            edited_expense_df = st.data_editor(
                st.session_state.expense_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "経費名": st.column_config.TextColumn("経費名", width="medium"),
                    "金額(万円)": st.column_config.NumberColumn("金額(万円)", format="%d", min_value=0, default=0),
                },
                key="expense_editor"
            )

        with cost_col2:
            st.markdown("**販管費(粗利Ⅱ計算用)**")
            brokerage_fee = st.number_input(
                "仲介手数料(万円)",
                value=0,
                step=10,
                help="売却時の仲介手数料"
            )

            st.markdown("**調達条件(PJ純利益計算用)**")
            ltv_rate = st.number_input(
                "LTV(対仕入れ値)(%)",
                value=80.0,
                step=5.0,
                help="Loan to Value:借入比率"
            )
            loan_interest_rate = st.number_input(
                "金利(対調達額・年率)(%)",
                value=2.0,
                step=0.1,
                help="借入金利"
            )
            upfront_rate = st.number_input(
                "Upfront(対調達額)(%)",
                value=1.0,
                step=0.1,
                help="融資手数料"
            )

        # その他経費の合計を計算
        other_expenses_df = edited_expense_df.copy()
        other_expenses_df["金額(万円)"] = pd.to_numeric(other_expenses_df["金額(万円)"], errors='coerce').fillna(0)
        other_expenses_total = other_expenses_df["金額(万円)"].sum()
        st.write("---")
        # --- 2. インセンティブ計算用パラメータ ---
        st.subheader("💰 インセンティブ計算パラメータ")

        # 固定値(2025年7月末基準、年1回見直し)
        KE_RATE = 10.0   # 自己資本コスト (%)
        KD_RATE = 2.8    # 負債コスト (%)
        TAX_RATE = 35.0  # 実効税率 (%)

        with st.expander("▼ インセンティブ計算条件を設定", expanded=True):
            inc_col1, inc_col2 = st.columns(2)

            with inc_col1:
                st.markdown("**📊 案件期間**")
                project_months = st.number_input(
                    "保有期間(月数)",
                    value=6,
                    min_value=1,
                    max_value=60,
                    help="仕入れから売却までの期間"
                )

                # 固定パラメータの表示(参考情報)
                st.caption(f"📌 固定パラメータ(2025年7月末基準)")
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

        # 固定値を変数に代入(後続の計算で使用)
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
                "面積(坪)": pd.Series(dtype='float'),
                "相場金額(坪)": pd.Series(dtype='int'),
                "提案金額(坪)": pd.Series(dtype='int'),
            })
        edited_df = st.data_editor(
            st.session_state.input_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "地権者名": st.column_config.TextColumn("地権者名", required=True),
                "面積(坪)": st.column_config.NumberColumn("面積(坪)", format="%.2f", min_value=0.0, default=0.0),
                "相場金額(坪)": st.column_config.NumberColumn("相場金額(坪)", format="%d 万円", min_value=0, default=0),
                "提案金額(坪)": st.column_config.NumberColumn("提案金額(坪)", format="%d 万円", min_value=0, default=0),
            },
            key="main_editor"
        )
        # --- 4. リアルタイム計算処理 ---
        calc_df = edited_df.copy()
        calc_df["面積(坪)"] = pd.to_numeric(calc_df["面積(坪)"], errors='coerce').fillna(0.0)
        calc_df["相場金額(坪)"] = pd.to_numeric(calc_df["相場金額(坪)"], errors='coerce').fillna(0)
        calc_df["提案金額(坪)"] = pd.to_numeric(calc_df["提案金額(坪)"], errors='coerce').fillna(0)
        # グロス金額を計算
        calc_df["相場金額(グロス)"] = calc_df["面積(坪)"] * calc_df["相場金額(坪)"]
        calc_df["提案金額(グロス)"] = calc_df["面積(坪)"] * calc_df["提案金額(坪)"]
        calc_df["差額(グロス)"] = calc_df["提案金額(グロス)"] - calc_df["相場金額(グロス)"]
        calc_df["一種単価"] = calc_df.apply(lambda x: x["提案金額(坪)"] / far_ratio if far_ratio > 0 else 0, axis=1)
        # 計算結果を表示
        if len(calc_df) > 0 and calc_df["面積(坪)"].sum() > 0:
            st.caption("📊 計算結果(自動計算)")
            display_df = calc_df[["地権者名", "面積(坪)", "相場金額(坪)", "提案金額(坪)", "提案金額(グロス)"]].copy()
            st.dataframe(
                display_df.style.format({
                    "面積(坪)": "{:.2f}",
                    "相場金額(坪)": "{:,.0f}",
                    "提案金額(坪)": "{:,.0f}",
                    "提案金額(グロス)": "{:,.0f}",
                }),
                hide_index=True,
                use_container_width=True
            )
        # 全体集計
        total_area_sum = calc_df["面積(坪)"].sum()
        total_offer_sum = calc_df["提案金額(グロス)"].sum()  # 仕入れ値(売上原価)
        total_market_sum = calc_df["相場金額(グロス)"].sum()

        # 出口グロス(売上)
        exit_gross = total_area_sum * far_ratio * exit_unit_price

        # === PL計算 ===
        # 諸経費
        acquisition_cost = total_offer_sum * acquisition_cost_rate / 100.0  # 物件取得経費
        total_expenses = acquisition_cost + other_expenses_total   # 諸経費合計

        # 粗利Ⅰ = 売上 - 売上原価 - 諸経費
        gross_profit_1 = exit_gross - total_offer_sum - total_expenses
        gross_profit_1_rate = gross_profit_1 / exit_gross * 100 if exit_gross > 0 else 0

        # 粗利Ⅱ = 粗利Ⅰ - 仲介手数料
        gross_profit_2 = gross_profit_1 - brokerage_fee
        gross_profit_2_rate = gross_profit_2 / exit_gross * 100 if exit_gross > 0 else 0

        # 調達コスト計算
        debt_amount = total_offer_sum * ltv_rate / 100.0  # 調達額 = 仕入れ値 × LTV
        holding_period_years = project_months / 12.0
        loan_interest = debt_amount * (loan_interest_rate / 100.0) * holding_period_years  # 金利
        upfront_fee = debt_amount * (upfront_rate / 100.0)  # Upfront
        total_financing_cost = loan_interest + upfront_fee  # 調達コスト合計

        # PJ純利益 = 粗利Ⅱ - 調達コスト
        pj_net_profit = gross_profit_2 - total_financing_cost
        pj_net_profit_rate = pj_net_profit / exit_gross * 100 if exit_gross > 0 else 0
        # --- 5. インセンティブ計算(粗利Ⅱベース) ---
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

        # 🔴 変更箇所: 粗利Ⅰから粗利Ⅱに変更
        # インセンティブ計算対象粗利 = 粗利Ⅱ - 資本コスト
        incentive_base_profit = gross_profit_2 - capital_cost

        # インセンティブ率取得
        incentive_rate = get_incentive_rate(grade, is_solo_pm)

        # 第三者のためにする契約の場合の補正
        if is_third_party_contract:
            if grade == "PM A1" or grade.startswith("PL"):
                incentive_rate *= 1.2

        # インセンティブ金額
        incentive_amount = incentive_base_profit * incentive_rate if incentive_base_profit > 0 else 0
        # --- 6. PL形式の結果表示 ---
        st.markdown("### 📊 PL(損益計算)")

        # PLテーブル形式で表示
        pl_col1, pl_col2 = st.columns([2, 1])

        with pl_col1:
            pl_data = [
                {"項目": "売上", "金額(万円)": f"{exit_gross:,.0f}", "率": ""},
                {"項目": "売上原価(仕入れ値)", "金額(万円)": f"{total_offer_sum:,.0f}", "率": ""},
                {"項目": "諸経費", "金額(万円)": f"{total_expenses:,.0f}", "率": ""},
                {"項目": "🔵 売上総利益(粗利Ⅰ)", "金額(万円)": f"{gross_profit_1:,.0f}", "率": f"{gross_profit_1_rate:.1f}%"},
                {"項目": "仲介手数料", "金額(万円)": f"{brokerage_fee:,.0f}", "率": ""},
                {"項目": "🔵 営業利益(粗利Ⅱ)", "金額(万円)": f"{gross_profit_2:,.0f}", "率": f"{gross_profit_2_rate:.1f}%"},
                {"項目": "調達コスト", "金額(万円)": f"{total_financing_cost:,.0f}", "率": ""},
                {"項目": "🟢 PJ純利益", "金額(万円)": f"{pj_net_profit:,.0f}", "率": f"{pj_net_profit_rate:.1f}%"},
            ]

            pl_df = pd.DataFrame(pl_data)
            st.dataframe(pl_df, hide_index=True, use_container_width=True)

            # 諸経費の内訳を折りたたみで表示
            with st.expander("▼ 諸経費の内訳"):
                expense_detail = [
                    {"項目": "物件取得経費", "金額(万円)": f"{acquisition_cost:,.0f}"}
                ]
                for _, row in other_expenses_df.iterrows():
                    if row["金額(万円)"] > 0:
                        expense_detail.append({
                            "項目": row["経費名"] if row["経費名"] else "その他",
                            "金額(万円)": f"{row['金額(万円)']:,.0f}"
                        })
                st.dataframe(pd.DataFrame(expense_detail), hide_index=True, use_container_width=True)

            # 調達コストの内訳を折りたたみで表示
            with st.expander("▼ 調達コストの内訳"):
                financing_detail = [
                    {"項目": f"調達額(LTV {ltv_rate:.0f}%)", "金額(万円)": f"{debt_amount:,.0f}"},
                    {"項目": f"保有期間", "金額(万円)": f"{project_months}ヶ月({holding_period_years:.2f}年)"},
                    {"項目": f"金利({loan_interest_rate:.2f}%)", "金額(万円)": f"{loan_interest:,.0f}"},
                    {"項目": f"Upfront({upfront_rate:.1f}%)", "金額(万円)": f"{upfront_fee:,.0f}"},
                ]
                st.dataframe(pd.DataFrame(financing_detail), hide_index=True, use_container_width=True)

        with pl_col2:
            # サマリーメトリクス
            st.metric("敷地面積合計", f"{total_area_sum:,.2f} 坪")

            if gross_profit_1 >= 0:
                st.metric("粗利Ⅰ", f"{gross_profit_1:,.0f} 万円", delta=f"{gross_profit_1_rate:.1f}%")
            else:
                st.metric("粗利Ⅰ", f"{gross_profit_1:,.0f} 万円", delta=f"{gross_profit_1_rate:.1f}%", delta_color="inverse")

            if gross_profit_2 >= 0:
                st.metric("粗利Ⅱ", f"{gross_profit_2:,.0f} 万円", delta=f"{gross_profit_2_rate:.1f}%")
            else:
                st.metric("粗利Ⅱ", f"{gross_profit_2:,.0f} 万円", delta=f"{gross_profit_2_rate:.1f}%", delta_color="inverse")

            if pj_net_profit >= 0:
                st.metric("PJ純利益", f"{pj_net_profit:,.0f} 万円", delta=f"{pj_net_profit_rate:.1f}%")
            else:
                st.metric("PJ純利益", f"{pj_net_profit:,.0f} 万円", delta=f"{pj_net_profit_rate:.1f}%", delta_color="inverse")
        # --- 7. インセンティブ計算結果 ---
        st.markdown("### 💵 インセンティブ計算結果")
        st.caption("※インセンティブは **粗利Ⅱ** から資本コストを差し引いた金額をベースに計算")

        inc_result_col1, inc_result_col2 = st.columns(2)

        with inc_result_col1:
            st.markdown("**計算プロセス**")

            # 計算過程をテーブルで表示
            calc_process = pd.DataFrame({
                "項目": [
                    "① 粗利Ⅱ",
                    "② 自己資本(Equity)",
                    "③ 借入(Debt)",
                    "④ 自己資本比率(we)",
                    "⑤ 負債比率(wd)",
                    "⑥ rWACC",
                    "⑦ 資本コスト",
                    "⑧ インセンティブ対象粗利(①-⑦)",
                ],
                "計算式/値": [
                    f"{gross_profit_2:,.0f} 万円",
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
                rate_display = f"{base_rate * 100:.0f}% + 7%(単独取纏め)= {incentive_rate * 100:.0f}%"
            if is_third_party_contract and (grade == "PM A1" or grade.startswith("PL")):
                rate_display += "(×1.2 第三者契約)"

            st.info(f"""
            **等級**: {grade}
            **インセンティブ率**: {rate_display}
            **対象粗利(粗利Ⅱ-資本コスト)**: {incentive_base_profit:,.0f} 万円
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
                st.markdown("**💰 相場金額 vs 提案金額(グロス)**")
                chart_data = calc_df[["地権者名", "相場金額(グロス)", "提案金額(グロス)"]].melt("地権者名", var_name="種別", value_name="金額(万円)")
                chart = alt.Chart(chart_data).mark_bar().encode(
                    x=alt.X('地権者名', sort=None, axis=alt.Axis(labelAngle=0)),
                    y='金額(万円)',
                    color=alt.Color('種別', scale=alt.Scale(domain=['相場金額(グロス)', '提案金額(グロス)'], range=['#A9A9A9', '#FF6347'])),
                    xOffset='種別',
                    tooltip=['地権者名', '種別', '金額(万円)']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
            with g_col2:
                st.markdown("**🏗 事業収支の構成**")
                if exit_gross > 0:
                    # コスト内訳
                    cost_breakdown = [
                        {"category": "売上原価", "value": max(total_offer_sum, 0)},
                        {"category": "諸経費", "value": max(total_expenses, 0)},
                        {"category": "仲介手数料", "value": max(brokerage_fee, 0)},
                        {"category": "調達コスト", "value": max(total_financing_cost, 0)},
                        {"category": "PJ純利益", "value": max(pj_net_profit, 0)},
                    ]
                    donut_data = pd.DataFrame(cost_breakdown)
                    donut_chart = alt.Chart(donut_data).mark_arc(innerRadius=50).encode(
                        theta=alt.Theta(field="value", type="quantitative"),
                        color=alt.Color(field="category", type="nominal", scale=alt.Scale(
                            domain=["売上原価", "諸経費", "仲介手数料", "調達コスト", "PJ純利益"],
                            range=['#D3D3D3', '#FFB6C1', '#DDA0DD', '#87CEEB', '#32CD32']
                        )),
                        tooltip=["category", "value"]
                    ).properties(height=300)
                    st.altair_chart(donut_chart, use_container_width=True)
                else:
                    st.warning("⚠️ データを入力してください")
            # 詳細テーブル
            with st.expander("▼ 地権者別計算詳細を見る", expanded=False):
                st.dataframe(calc_df.style.format({
                    "面積(坪)": "{:.2f}",
                    "相場金額(坪)": "{:,.0f}",
                    "提案金額(坪)": "{:,.0f}",
                    "相場金額(グロス)": "{:,.0f}",
                    "提案金額(グロス)": "{:,.0f}",
                    "差額(グロス)": "{:,.0f}",
                    "一種単価": "{:,.2f}"
                }), use_container_width=True)
        # --- 9. 保存機能 ---
        st.write("---")
        c_save1, c_save2 = st.columns([3, 1])
        save_name = c_save1.text_input("プロジェクト名をつけて保存", placeholder="例:日本橋計画_Ver1")
        if c_save2.button("💾 プロジェクトを保存", type="primary"):
            if save_name and len(calc_df) > 0:
                save_project(save_name, total_area_sum, far, exit_unit_price, calc_df)
                st.success(f"「{save_name}」を保存しました!")
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
                            "name": "地権者名", "area": "面積(坪)", "market_price": "相場金額(坪)", "offer_price": "提案金額(坪)"
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
                                    "面積(坪)": l_row['area'],
                                    "相場金額(坪)": l_row['market_price'],
                                    "提案金額(坪)": l_row['offer_price']
                                })
                            st.session_state.input_df = pd.DataFrame(loaded_data).astype({
                                "地権者名": "str", "面積(坪)": "float", "相場金額(坪)": "int", "提案金額(坪)": "int"
                            })
                            st.session_state.target_far = project['target_far']
                            st.session_state.exit_unit_price = project['exit_unit_price']
                            st.toast("ロードしました。シミュレーション画面へ移動してください", icon="✅")
        else:
            st.write("保存データはありません。")
if __name__ == '__main__':
    main()
