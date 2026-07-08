# hr/views/finance_views.py
#
# Finance Dashboard — Payroll processing flow:
#   1. Finance generates payroll (creates PayrollRecord rows in 'Pending' state)
#   2. Finance reviews and marks records 'Reviewed'
#   3. HR sees reviewed records and gives final 'HR Approved' status
#   4. Finance marks individual records 'Paid'

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone

from hr.views.attendance_views import is_hr


def _is_finance_or_hr(user) -> bool:
    """Finance role or HR role can access the finance dashboard."""
    if user.is_superuser or user.is_staff:
        return True
    try:
        from hr.models import Employee
        emp = Employee.objects.get(user=user)
        if emp.role and emp.role.name.lower() in {'hr', 'admin', 'hr manager', 'finance', 'accountant'}:
            return True
    except Exception:
        pass
    return False


@login_required(login_url='/login/')
def finance_dashboard(request):
    """
    Finance Dashboard — central hub for payroll generation, review, and approval flow.
    """
    if not _is_finance_or_hr(request.user):
        return redirect('/dashboard/employee/')

    from hr.models import PayrollRecord
    from hr.services.payroll_service import generate_payroll, mark_paid

    # ── Generate Payroll ────────────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'generate':
            from datetime import date
            try:
                period_start = date.fromisoformat(request.POST.get('period_start', ''))
                period_end   = date.fromisoformat(request.POST.get('period_end', ''))
                result = generate_payroll(period_start, period_end)
                messages.success(
                    request,
                    f"Payroll generated: {result['created']} records created, "
                    f"{result['skipped']} skipped."
                )
                if result['errors']:
                    messages.warning(request, "Errors: " + "; ".join(result['errors'][:5]))
            except ValueError:
                messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
            except Exception as e:
                messages.error(request, f"Payroll generation failed: {e}")
            return redirect('finance_dashboard')

        elif action == 'mark_reviewed':
            # Finance marks a payroll record as Reviewed (ready for HR sign-off)
            record_id = request.POST.get('record_id')
            if record_id:
                try:
                    rec = PayrollRecord.objects.get(pk=record_id)
                    if rec.payment_status == 'Pending':
                        rec.payment_status = 'Reviewed'
                        rec.save(update_fields=['payment_status'])
                        messages.success(request, f"Record for {rec.employee.get_full_name()} marked as Reviewed.")
                    else:
                        messages.warning(request, "Only Pending records can be marked Reviewed.")
                except PayrollRecord.DoesNotExist:
                    messages.error(request, "Record not found.")
            return redirect('finance_dashboard')

        elif action == 'mark_reviewed_batch':
            # Mark all Pending records for a given period as Reviewed
            period_start_str = request.POST.get('batch_period_start', '')
            period_end_str   = request.POST.get('batch_period_end', '')
            try:
                from datetime import date
                ps = date.fromisoformat(period_start_str)
                pe = date.fromisoformat(period_end_str)
                updated = PayrollRecord.objects.filter(
                    period_start=ps, period_end=pe, payment_status='Pending'
                ).update(payment_status='Reviewed')
                messages.success(request, f"{updated} payroll record(s) marked as Reviewed and sent to HR for approval.")
            except Exception as e:
                messages.error(request, f"Batch review failed: {e}")
            return redirect('finance_dashboard')

        elif action == 'hr_approve':
            # HR gives final approval on a Reviewed record
            if not is_hr(request.user):
                messages.error(request, "Only HR can give final payroll approval.")
                return redirect('finance_dashboard')
            record_id = request.POST.get('record_id')
            if record_id:
                try:
                    rec = PayrollRecord.objects.get(pk=record_id)
                    if rec.payment_status == 'Reviewed':
                        rec.payment_status = 'HR Approved'
                        rec.save(update_fields=['payment_status'])
                        messages.success(request, f"Payroll for {rec.employee.get_full_name()} approved by HR.")
                    else:
                        messages.warning(request, "Only Reviewed records can be HR-approved.")
                except PayrollRecord.DoesNotExist:
                    messages.error(request, "Record not found.")
            return redirect('finance_dashboard')

        elif action == 'hr_approve_batch':
            # HR approves all Reviewed records for a period
            if not is_hr(request.user):
                messages.error(request, "Only HR can give final payroll approval.")
                return redirect('finance_dashboard')
            period_start_str = request.POST.get('batch_period_start', '')
            period_end_str   = request.POST.get('batch_period_end', '')
            try:
                from datetime import date
                ps = date.fromisoformat(period_start_str)
                pe = date.fromisoformat(period_end_str)
                updated = PayrollRecord.objects.filter(
                    period_start=ps, period_end=pe, payment_status='Reviewed'
                ).update(payment_status='HR Approved')
                messages.success(request, f"{updated} payroll record(s) approved by HR.")
            except Exception as e:
                messages.error(request, f"Batch HR approval failed: {e}")
            return redirect('finance_dashboard')

        elif action == 'mark_paid':
            record_id = request.POST.get('record_id')
            if record_id:
                try:
                    rec = PayrollRecord.objects.get(pk=record_id)
                    if rec.payment_status == 'HR Approved':
                        rec.payment_status = 'Paid'
                        rec.save(update_fields=['payment_status'])
                        messages.success(request, f"Payroll for {rec.employee.get_full_name()} marked as Paid.")
                    else:
                        messages.warning(request, "Only HR Approved records can be marked Paid.")
                except PayrollRecord.DoesNotExist:
                    messages.error(request, "Record not found.")
            return redirect('finance_dashboard')

    # ── GET — Build page context ────────────────────────────────────────────
    query    = request.GET.get('q', '').strip()
    month    = request.GET.get('month', '')
    year     = request.GET.get('year', '')
    status_f = request.GET.get('status', '')

    from hr.services.payroll_service import get_all_payroll_records
    records = get_all_payroll_records(query=query, month=month, year=year, status=status_f)

    # Summary counts
    pending_count     = PayrollRecord.objects.filter(payment_status='Pending').count()
    reviewed_count    = PayrollRecord.objects.filter(payment_status='Reviewed').count()
    approved_count    = PayrollRecord.objects.filter(payment_status='HR Approved').count()
    paid_count        = PayrollRecord.objects.filter(payment_status='Paid').count()

    total_gross = sum(r.gross_salary for r in records)
    total_net   = sum(r.net_salary   for r in records)
    total_tax   = sum(r.income_tax   for r in records)
    total_pension = sum(r.pension    for r in records)

    context = {
        'records':          records,
        'search_query':     query,
        'month':            month,
        'year':             year,
        'status_f':         status_f,
        'total_gross':      total_gross,
        'total_net':        total_net,
        'total_tax':        total_tax,
        'total_pension':    total_pension,
        'pending_count':    pending_count,
        'reviewed_count':   reviewed_count,
        'approved_count':   approved_count,
        'paid_count':       paid_count,
        'active_page':      'finance_dashboard',
        'today':            timezone.localdate().isoformat(),
        'user_is_hr':       is_hr(request.user),
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December')
        ],
        'years':    [2024, 2025, 2026],
        'statuses': ['Pending', 'Reviewed', 'HR Approved', 'Paid', 'On Hold'],
    }
    return render(request, 'hr/finance_dashboard.html', context)
