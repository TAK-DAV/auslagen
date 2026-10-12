from django.urls import path

from portal import review_views, views

app_name = "portal"

urlpatterns = [
    path("anmelden/", views.login_request, name="login_request"),
    path("link/<str:token>/", views.magic_login, name="magic_login"),
    path("abmelden/", views.portal_logout, name="logout"),
    path("datenschutz/", views.privacy, name="privacy"),
    path("profil/", views.profile_edit, name="profile"),
    path("abrechnungen/", views.report_list, name="report_list"),
    path("abrechnungen/neu/", views.report_create, name="report_create"),
    path("abrechnungen/<int:pk>/", views.report_detail, name="report_detail"),
    path("abrechnungen/<int:pk>/einreichen/", views.report_submit, name="report_submit"),
    path(
        "abrechnungen/<int:report_pk>/position/neu/",
        views.line_create,
        name="line_create",
    ),
    path(
        "abrechnungen/<int:report_pk>/position/<int:line_pk>/loeschen/",
        views.line_delete,
        name="line_delete",
    ),
    path("team/", review_views.team_home, name="team_home"),
    path("team/anmelden/", views.staff_login, name="staff_login"),
    path("team/2fa/", views.staff_totp, name="staff_totp"),
    path("team/2fa/bestaetigen/", views.staff_totp_confirm_setup, name="staff_totp_confirm"),
    path("pruefung/", review_views.review_queue, name="review_queue"),
    path("pruefung/<int:pk>/", review_views.review_report, name="review_report"),
    path(
        "pruefung/<int:report_pk>/position/<int:line_pk>/freigeben/",
        review_views.review_approve_line,
        name="review_approve_line",
    ),
    path("pruefung/<int:pk>/rueckfrage/", review_views.review_question, name="review_question"),
    path("schatzmeister/", review_views.treasurer_queue, name="treasurer_queue"),
    path("schatzmeister/<int:pk>/", review_views.treasurer_report, name="treasurer_report"),
    path(
        "schatzmeister/<int:pk>/freigeben/",
        review_views.treasurer_approve_view,
        name="treasurer_approve",
    ),
    path("teil/steuersaetze/", views.tax_rates_partial, name="tax_rates_partial"),
]
