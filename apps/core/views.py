from django.http import JsonResponse


def home(request):
    return JsonResponse({
        "message": "QuantumStock AI API is running successfully 🚀",
        "status": "ok",
        "version": "2.0.0",
    })
