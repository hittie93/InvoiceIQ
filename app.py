
import base64
import json
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.database import initialise_database, get_history, get_steps
from src.workflow import process_invoice


st.set_page_config(
    page_title="InvoiceIQ",
    page_icon="🧾",
    layout="wide"
)

initialise_database()


STATUS_COLORS = {
    "APPROVED": "#2563EB",
    "PENDING_REVIEW": "#F59E0B",
    "REJECTED": "#DC2626",
    "PROCESSING_FAILED": "#6B7280",
    "NOT_DECIDED": "#9CA3AF",
}

st.markdown("""
<style>

/* Main application layout */
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1500px;
}

/* Main title */
h1 {
    font-weight: 750 !important;
    letter-spacing: -1px;
}

/* Section headings */
h2, h3 {
    font-weight: 650 !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background-color: #262B36;
    border: 1px solid #3B4352;
    padding: 20px 22px;
    border-radius: 13px;
    min-height: 125px;
}

/* Metric labels */
div[data-testid="stMetricLabel"] {
    color: #D1D5DB !important;
    font-size: 15px !important;
    font-weight: 600 !important;
}

/* Metric values */
div[data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-size: 34px !important;
    font-weight: 750 !important;
}

/* Metric delta */
div[data-testid="stMetricDelta"] {
    font-size: 13px !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    border-right: 1px solid #303642;
}

/* Dataframes */
div[data-testid="stDataFrame"] {
    border: 1px solid #353B46;
    border-radius: 9px;
}

/* Buttons */
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
}

/* Dividers */
hr {
    border-color: #343A46;
}

</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# COMMON APPLICATION HEADER
# --------------------------------------------------

st.title("🧾 InvoiceIQ")

st.caption(
    "AI-powered accounts payable automation | "
    "Extract · Validate · Reconcile · Decide"
)


# --------------------------------------------------
# SIDEBAR NAVIGATION
# --------------------------------------------------

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Process invoice", "Execution history"]
)

st.sidebar.caption("Prototype environment")

st.sidebar.write(
    f"LLM (Gemini): {'Connected' if GEMINI_API_KEY else 'API key required'}"
)

st.sidebar.caption(f"Model: {GEMINI_MODEL}")


# --------------------------------------------------
# LOAD HISTORY
# --------------------------------------------------

history = get_history()


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

if page == "Dashboard":

    st.subheader("Operations overview")

    df = pd.DataFrame(history)

    if df.empty:

        st.info(
            "No invoices processed yet. "
            "Go to **Process invoice** to run your first invoice."
        )

    else:

        processing = df.get(
            "processing_status",
            pd.Series("COMPLETED", index=df.index)
        ).fillna("COMPLETED")

        decisions = df.get(
            "decision",
            pd.Series("NOT_DECIDED", index=df.index)
        ).fillna("NOT_DECIDED")

        total = len(df)

        approved = int((decisions == "APPROVED").sum())
        pending = int((decisions == "PENDING_REVIEW").sum())
        rejected = int((decisions == "REJECTED").sum())
        failed = int((processing == "PROCESSING_FAILED").sum())

        # --------------------------------------------------
        # OPERATIONS METRICS
        # --------------------------------------------------

        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("Total runs", total)
        c2.metric("Approved", approved)
        c3.metric("Pending review", pending)
        c4.metric("Rejected", rejected)
        c5.metric("Processing failed", failed)

        st.write("")

        # --------------------------------------------------
        # NORMALIZE CHART STATUSES
        # --------------------------------------------------

        chart_df = df.copy()

        chart_df["display_status"] = decisions

        chart_df.loc[
            processing == "PROCESSING_FAILED",
            "display_status"
        ] = "PROCESSING_FAILED"

        # Keep the chart restricted to known statuses.
        chart_df["display_status"] = chart_df[
            "display_status"
        ].where(
            chart_df["display_status"].isin(STATUS_COLORS),
            "NOT_DECIDED"
        )

        left, right = st.columns(2)

        # --------------------------------------------------
        # DECISION DISTRIBUTION
        # --------------------------------------------------

        with left:

            st.markdown("### Decision distribution")

            counts = (
                chart_df["display_status"]
                .value_counts()
                .rename_axis("Status")
                .reset_index(name="Count")
            )

            fig_pie = px.pie(
                counts,
                names="Status",
                values="Count",
                hole=0.48,
                color="Status",
                color_discrete_map=STATUS_COLORS,
                title="Invoice processing outcomes"
            )

            fig_pie.update_traces(
                textposition="inside",
                textinfo="percent+label",
                insidetextfont=dict(
                    color="white",
                    size=12
                ),
                marker=dict(
                    line=dict(
                        color="#17191F",
                        width=2
                    )
                ),
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Invoices: %{value}<br>"
                    "Share: %{percent}"
                    "<extra></extra>"
                )
            )

            fig_pie.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(
                    color="#E5E7EB",
                    size=12
                ),
                legend_title_text="Decision",
                title_font=dict(
                    size=17,
                    color="#F9FAFB"
                ),
                margin=dict(
                    l=15,
                    r=15,
                    t=65,
                    b=20
                ),
                height=390
            )

            st.plotly_chart(
                fig_pie,
                use_container_width=True
            )

        # --------------------------------------------------
        # RECENT PROCESSING RUNS
        # --------------------------------------------------

        with right:

            st.markdown("### Recent processing runs")

            recent_df = chart_df.head(10).copy()

            recent_df["created_at"] = pd.to_datetime(
                recent_df["created_at"],
                errors="coerce"
            )

            recent_df["duration_ms"] = pd.to_numeric(
                recent_df.get(
                    "duration_ms",
                    pd.Series(0, index=recent_df.index)
                ),
                errors="coerce"
            ).fillna(0)

            if "invoice_number" in recent_df.columns:
                recent_df["run_label"] = (
                    recent_df["invoice_number"]
                    .fillna("No invoice number")
                    .astype(str)
                )
            else:
                recent_df["run_label"] = recent_df["run_id"].astype(str)

            fig_runs = px.bar(
                recent_df.sort_values("created_at"),
                x="run_label",
                y="duration_ms",
                color="display_status",
                color_discrete_map=STATUS_COLORS,
                title="Processing time by invoice",
                labels={
                    "run_label": "Invoice",
                    "duration_ms": "Duration (ms)",
                    "display_status": "Decision"
                },
                hover_data=["run_id", "created_at"]
            )

            fig_runs.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(
                    color="#E5E7EB",
                    size=11
                ),
                title_font=dict(
                    size=17,
                    color="#F9FAFB"
                ),
                xaxis=dict(
                    title="Invoice",
                    tickangle=-35,
                    gridcolor="#343A46"
                ),
                yaxis=dict(
                    title="Processing duration (ms)",
                    gridcolor="#343A46",
                    rangemode="tozero"
                ),
                legend_title_text="Decision",
                margin=dict(
                    l=15,
                    r=15,
                    t=65,
                    b=75
                ),
                height=390
            )

            st.plotly_chart(
                fig_runs,
                use_container_width=True
            )

        # --------------------------------------------------
        # RECENT INVOICES TABLE
        # --------------------------------------------------

        st.divider()

        st.subheader("Recent invoices")

        columns = [
            c for c in (
                "created_at",
                "invoice_number",
                "vendor_name",
                "total_amount",
                "decision",
                "processing_status",
                "duration_ms"
            )
            if c in df.columns
        ]

        st.dataframe(
            df[columns].head(10),
            use_container_width=True,
            hide_index=True
        )


# --------------------------------------------------
# PROCESS INVOICE
# --------------------------------------------------

elif page == "Process invoice":

    st.subheader("Process a new invoice")

    st.write(
        "Upload a PDF invoice. InvoiceIQ extracts its fields, "
        "validates vendor and PO data, reconciles amounts "
        "and produces an explainable decision."
    )

    uploaded = st.file_uploader(
        "Choose invoice PDF",
        type=["pdf"]
    )

    if uploaded:

        pdf_bytes = uploaded.getvalue()

        st.write(
            f"**File:** {uploaded.name} · "
            f"{uploaded.size / 1024:.1f} KB"
        )

        left, right = st.columns(2)

        with left:

            st.download_button(
                "Download uploaded PDF",
                data=pdf_bytes,
                file_name=uploaded.name,
                mime="application/pdf"
            )

        with right:

            st.caption(
                "Source document is retained only in this active "
                "session; the database stores its SHA-256 fingerprint."
            )

        with st.expander("Preview source invoice", expanded=False):

            encoded = base64.b64encode(pdf_bytes).decode("ascii")

            st.markdown(
                f'<iframe src="data:application/pdf;base64,{encoded}" '
                'width="100%" height="650" '
                'type="application/pdf"></iframe>',
                unsafe_allow_html=True
            )

        if st.button("Run invoice workflow", type="primary"):

            progress_area = st.empty()
            stage_events = {}

            def progress(step, status, message):

                stage_events[step] = {
                    "Stage": step,
                    "Status": status,
                    "Details": message
                }

                progress_area.dataframe(
                    pd.DataFrame(list(stage_events.values())),
                    use_container_width=True,
                    hide_index=True
                )

            temp_path = None

            try:

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".pdf"
                ) as tmp:

                    tmp.write(pdf_bytes)
                    temp_path = tmp.name

                with st.spinner("Executing invoice workflow..."):

                    result = process_invoice(
                        temp_path,
                        progress,
                        source_filename=uploaded.name
                    )

                st.divider()

                st.subheader("Processing decision")

                if result.decision == "APPROVED":

                    st.success("APPROVED")

                elif result.decision == "REJECTED":

                    st.error("REJECTED")

                else:

                    st.warning("PENDING HUMAN REVIEW")

                st.write(result.reason)

                st.caption(f"Run ID: {result.run_id}")

                first_col, second_col = st.columns(2)

                with first_col:

                    st.subheader("Extracted invoice information")

                    st.json(result.invoice)

                with second_col:

                    st.subheader("Field evidence and warnings")

                    evidence_rows = [
                        {"Field": field, **details}
                        for field, details in result.field_evidence.items()
                    ]

                    st.dataframe(
                        pd.DataFrame(evidence_rows),
                        use_container_width=True,
                        hide_index=True
                    )

                st.subheader("Validation results")

                check_rows = [
                    c.model_dump()
                    for c in result.checks
                ]

                st.dataframe(
                    pd.DataFrame(check_rows),
                    use_container_width=True,
                    hide_index=True
                )

                run_row = next(
                    (
                        item for item in get_history()
                        if item["run_id"] == result.run_id
                    ),
                    {}
                )

                metric1, metric2 = st.columns(2)

                metric1.metric(
                    "Processing duration",
                    f"{run_row.get('duration_ms', 0)} ms"
                )

                metric2.metric(
                    "Exceptions",
                    run_row.get("exception_count", 0)
                )

            except Exception as exc:

                st.error(
                    f"Workflow could not complete: {exc}"
                )

                st.info(
                    "The failed run is recorded in Execution history. "
                    "Check Gemini API availability, PDF readability "
                    "and Tesseract installation."
                )

            finally:

                if temp_path:

                    try:
                        Path(temp_path).unlink(missing_ok=True)

                    except OSError:
                        pass


# --------------------------------------------------
# EXECUTION HISTORY
# --------------------------------------------------

elif page == "Execution history":

    st.subheader("Execution history")

    if not history:

        st.info("No execution history yet.")

    else:

        df = pd.DataFrame(history)

        display_columns = [
            c for c in (
                "created_at",
                "run_id",
                "processing_status",
                "invoice_number",
                "vendor_name",
                "total_amount",
                "decision",
                "reason",
                "duration_ms",
                "exception_count"
            )
            if c in df.columns
        ]

        st.dataframe(
            df[display_columns],
            use_container_width=True,
            hide_index=True
        )

        run_ids = df["run_id"].tolist()

        selected = st.selectbox(
            "Inspect a run",
            run_ids
        )

        if selected:

            run = next(
                item for item in history
                if item["run_id"] == selected
            )

            st.subheader("Run details")

            if run.get("processing_status") == "PROCESSING_FAILED":

                st.error(
                    run.get("error_message")
                    or run.get("reason")
                    or "Processing failed."
                )

            elif run.get("decision") == "APPROVED":

                st.success("APPROVED")

            elif run.get("decision") == "REJECTED":

                st.error("REJECTED")

            elif run.get("decision") == "PENDING_REVIEW":

                st.warning("PENDING HUMAN REVIEW")

            if (
                run.get("result_json")
                and run["result_json"] != "{}"
            ):

                try:

                    st.json(
                        json.loads(run["result_json"])
                    )

                except (TypeError, json.JSONDecodeError):

                    st.code(run["result_json"])

            st.write("Workflow audit trail")

            steps = get_steps(selected)

            if steps:

                st.dataframe(
                    pd.DataFrame(steps),
                    use_container_width=True,
                    hide_index=True
                )

            st.caption(
                f"Duration: {run.get('duration_ms') or 'N/A'} ms · "
                f"Exceptions: {run.get('exception_count', 0)}"
            )
