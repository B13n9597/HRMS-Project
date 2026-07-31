from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from hr.services import employee_service

def role_required(*allowed_roles):
    """
    Decorator for views that checks whether a user has one of the required roles.
    
    Roles can be specified as:
    'DEAN', 'CEO', 'PRESIDENT', 'HR_ADMIN', 'HR', 'SUPERVISOR', 'EMPLOYEE'
    
    If unauthenticated: Redirects to /login/.
    If authenticated but unauthorized: Returns HTTP 403 Forbidden.
    """
    # Normalize allowed roles to canonical keys
    normalized_allowed = set()
    for role in allowed_roles:
        r_upper = str(role).strip().upper()
        if r_upper in {'DEAN', 'ACADEMIC_DEAN'}:
            normalized_allowed.add(employee_service.ROLE_DEAN)
        elif r_upper in {'CEO', 'PRESIDENT', 'CHIEF_EXECUTIVE_OFFICER'}:
            normalized_allowed.add(employee_service.ROLE_CEO)
        elif r_upper in {'HR_ADMIN', 'HR', 'ADMIN', 'HR_DIRECTOR', 'HR_MANAGER'}:
            normalized_allowed.add(employee_service.ROLE_HR)
        elif r_upper in {'SUPERVISOR', 'DEPARTMENT_HEAD', 'TEAM_LEAD'}:
            normalized_allowed.add(employee_service.ROLE_SUPERVISOR)
        elif r_upper in {'EMPLOYEE', 'STAFF'}:
            normalized_allowed.add(employee_service.ROLE_EMPLOYEE)
        else:
            normalized_allowed.add(str(role).lower())

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({'error': 'Authentication required'}, status=401)
                return redirect(f"/login/?next={request.path}")

            user_role = employee_service.get_role_key(request.user)
            if user_role not in normalized_allowed and not request.user.is_superuser:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({'error': '403 Forbidden: Access Denied'}, status=403)
                return HttpResponseForbidden(
                    "<h1>403 Forbidden</h1><p>You do not have permission to access this dashboard or resource.</p>"
                )

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
