"""Booking CSV, SEPA pain.001 and receipt ZIP for a payment run.

The tool never initiates bank transfers – it only produces upload files.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring

from django.utils import timezone

from claims.donations import donation_booking_lines
from claims.models import ExpenseReport, LineItem, PaymentRun, ReportStatus
from masterdata.models import OrganizationSettings
from tak.fields import euros

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class BookingRow:
    booking_date: date
    document_number: str
    account: str
    contra: str
    cost_center: str
    sphere: str
    net: Decimal
    tax: Decimal
    rate: str
    tax_country: str
    vat_result: str
    gross: Decimal
    text: str


def document_number_for(line: LineItem) -> str:
    if line.document_number:
        return line.document_number
    # FACHLICH OFFEN: official receipt number sequence not defined yet.
    return f"A-{line.report_id}-{line.pk}"


def booking_rows_for_report(report: ExpenseReport) -> list[BookingRow]:
    settings = OrganizationSettings.load()
    contra = settings.creditor_account.number if settings.creditor_account_id else ""
    rows = []
    for line in report.lines.select_related("cost_center", "sphere", "tax_rate", "account").all():
        account = line.account.number if line.account_id else ""
        rate = f"{line.tax_rate.rate_percent:.2f}" if line.tax_rate_id else "0.00"
        rows.append(
            BookingRow(
                booking_date=line.expense_date,
                document_number=document_number_for(line),
                account=account,
                contra=contra,
                cost_center=line.cost_center.name,
                sphere=line.sphere.name if line.sphere_id else "",
                net=line.net or ZERO,
                tax=line.tax_amount or ZERO,
                rate=rate,
                tax_country=line.receipt_country or line.cost_center.country,
                vat_result=line.vat_result or "",
                gross=line.gross,
                text=(line.purpose or line.description or line.get_expense_type_display())[:120],
            )
        )
    for donation in donation_booking_lines(report):
        rows.append(
            BookingRow(
                booking_date=report.submitted_at.date() if report.submitted_at else timezone.localdate(),
                document_number=f"S-{report.pk}",
                account=donation.account_number,
                contra=donation.contra_account,
                cost_center="",
                sphere="Ideeller Bereich",
                net=donation.amount,
                tax=ZERO,
                rate="0.00",
                tax_country="",
                vat_result="KEINE",
                gross=donation.amount,
                text=donation.text,
            )
        )
    return rows


def booking_rows_for_run(payment_run: PaymentRun) -> list[BookingRow]:
    rows = []
    for report in payment_run.reports.prefetch_related("lines").all():
        rows.extend(booking_rows_for_report(report))
    return rows


def csv_booking_list(payment_run: PaymentRun) -> bytes:
    """UTF-8 with BOM, semicolon – opens cleanly in German Excel."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            "Datum",
            "Belegnummer",
            "Sachkonto",
            "Gegenkonto",
            "Kostenstelle",
            "Sphäre",
            "Netto",
            "Steuer",
            "Satz",
            "Steuerland",
            "Vorsteuerergebnis",
            "Brutto",
            "Buchungstext",
        ]
    )
    for row in booking_rows_for_run(payment_run):
        writer.writerow(
            [
                row.booking_date.isoformat(),
                row.document_number,
                row.account,
                row.contra,
                row.cost_center,
                row.sphere,
                f"{row.net:.2f}".replace(".", ","),
                f"{row.tax:.2f}".replace(".", ","),
                row.rate.replace(".", ","),
                row.tax_country,
                row.vat_result,
                f"{row.gross:.2f}".replace(".", ","),
                row.text,
            ]
        )
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _text(parent, tag: str, value: str):
    el = SubElement(parent, tag)
    el.text = value
    return el


def sepa_pain001(payment_run: PaymentRun) -> bytes:
    settings = OrganizationSettings.load()
    if not settings.bank_iban or not settings.bank_account_holder:
        raise ValueError("Vereinskonto (IBAN und Kontoinhaber) fehlt in den Einstellungen.")

    reports = [
        r
        for r in payment_run.reports.select_related("submitter").all()
        if r.payout_amount > 0
    ]
    if not reports:
        raise ValueError("Keine auszuzahlenden Beträge in diesem Lauf.")

    msg_id = f"TAK-{payment_run.pk}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
    created = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")
    ctrl_sum = euros(sum((r.payout_amount for r in reports), ZERO))
    nb_txs = str(len(reports))

    root = Element(
        "Document",
        {
            "xmlns": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        },
    )
    cstmr = SubElement(root, "CstmrCdtTrfInitn")
    grp = SubElement(cstmr, "GrpHdr")
    _text(grp, "MsgId", msg_id)
    _text(grp, "CreDtTm", created)
    _text(grp, "NbOfTxs", nb_txs)
    _text(grp, "CtrlSum", f"{ctrl_sum:.2f}")
    init = SubElement(grp, "InitgPty")
    _text(init, "Nm", settings.bank_account_holder[:70])

    pmt = SubElement(cstmr, "PmtInf")
    _text(pmt, "PmtInfId", f"PMT-{payment_run.pk}")
    _text(pmt, "PmtMtd", "TRF")
    _text(pmt, "NbOfTxs", nb_txs)
    _text(pmt, "CtrlSum", f"{ctrl_sum:.2f}")
    pmt_tp = SubElement(pmt, "PmtTpInf")
    svc = SubElement(pmt_tp, "SvcLvl")
    _text(svc, "Cd", "SEPA")
    _text(pmt, "ReqdExctnDt", timezone.localdate().isoformat())
    dbtr = SubElement(pmt, "Dbtr")
    _text(dbtr, "Nm", settings.bank_account_holder[:70])
    dbtr_acct = SubElement(pmt, "DbtrAcct")
    dbtr_id = SubElement(dbtr_acct, "Id")
    _text(dbtr_id, "IBAN", settings.bank_iban)
    dbtr_agt = SubElement(pmt, "DbtrAgt")
    fin = SubElement(dbtr_agt, "FinInstnId")
    if settings.bank_bic:
        _text(fin, "BIC", settings.bank_bic)
    else:
        othr = SubElement(fin, "Othr")
        _text(othr, "Id", "NOTPROVIDED")

    for report in reports:
        person = report.submitter
        if not person.iban:
            raise ValueError(f"IBAN fehlt bei {person.email} (Abrechnung {report.pk}).")
        tx = SubElement(pmt, "CdtTrfTxInf")
        pmt_id = SubElement(tx, "PmtId")
        _text(pmt_id, "EndToEndId", f"AUSL-{report.pk}")
        amt = SubElement(tx, "Amt")
        instd = SubElement(amt, "InstdAmt", {"Ccy": "EUR"})
        instd.text = f"{report.payout_amount:.2f}"
        cdtr_agt = SubElement(tx, "CdtrAgt")
        fin2 = SubElement(cdtr_agt, "FinInstnId")
        othr2 = SubElement(fin2, "Othr")
        _text(othr2, "Id", "NOTPROVIDED")
        cdtr = SubElement(tx, "Cdtr")
        _text(cdtr, "Nm", (person.get_full_name() or person.email)[:70])
        cdtr_acct = SubElement(tx, "CdtrAcct")
        cdtr_id = SubElement(cdtr_acct, "Id")
        _text(cdtr_id, "IBAN", person.iban)
        rmt = SubElement(tx, "RmtInf")
        _text(rmt, "Ustrd", f"Auslagen Abrechnung {report.pk}"[:140])

    xml = tostring(root, encoding="utf-8", xml_declaration=True)
    return xml


def receipts_zip(payment_run: PaymentRun) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for report in payment_run.reports.prefetch_related("lines__receipt", "lines__cost_center").all():
            for line in report.lines.all():
                if not line.receipt_id or not line.receipt.file:
                    continue
                year = line.calendar_year or line.expense_date.year
                folder = line.cost_center.filing_folder or "Sonstiges"
                name = document_number_for(line)
                ext = ""
                original = line.receipt.original_name or line.receipt.file.name
                if "." in original:
                    ext = "." + original.rsplit(".", 1)[-1]
                arcname = f"{year}/{folder}/{name}{ext}"
                with line.receipt.file.open("rb") as handle:
                    archive.writestr(arcname, handle.read())
    return buffer.getvalue()


def eligible_reports_for_payment():
    return (
        ExpenseReport.objects.filter(status=ReportStatus.APPROVED)
        .exclude(donation_choice="VOLLVERZICHT")
        .select_related("submitter")
        .prefetch_related("lines")
    )
