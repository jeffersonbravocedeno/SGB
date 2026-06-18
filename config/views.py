from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    return render(request, "base.html")


def health(request):
    return HttpResponse("SIAB OK", content_type="text/plain")
