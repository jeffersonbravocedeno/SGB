from django.db import models


class Tiposocio(models.Model):
    idtiposocio = models.IntegerField(primary_key=True)
    nombretiposocio = models.CharField(unique=True, max_length=100)
    roltiposocio = models.CharField(unique=True, max_length=50)
    descripciondetiposocio = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.nombretiposocio

    class Meta:
        managed = False
        db_table = 'tiposocio'
        verbose_name = 'Tipo de socio'
        verbose_name_plural = 'Tipos de socio'


class Metodopago(models.Model):
    idmetodopago = models.IntegerField(primary_key=True)
    nombremetodopago = models.CharField(unique=True, max_length=50)
    descripcionmetodopago = models.CharField(max_length=200, blank=True, null=True)
    estadometodopago = models.BooleanField(blank=True, null=True)
    urlmetodopago = models.CharField(max_length=255)

    def __str__(self):
        return self.nombremetodopago

    class Meta:
        managed = False
        db_table = 'metodopago'
        verbose_name = 'Metodo de pago'
        verbose_name_plural = 'Metodos de pago'


class Plataformajuego(models.Model):
    idplataformajuego = models.IntegerField(primary_key=True)
    nombreplataforma = models.CharField(unique=True, max_length=25)
    urlplataforma = models.CharField(max_length=255)
    descripcionplataforma = models.CharField(max_length=200, blank=True, null=True)
    estadoplataforma = models.BooleanField()
    fechaadquisicionlicencia = models.DateField(blank=True, null=True)
    fechavencimientolicencia = models.DateField(blank=True, null=True)
    contactoplataforma = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.nombreplataforma

    class Meta:
        managed = False
        db_table = 'plataformajuego'
        verbose_name = 'Plataforma de juego'
        verbose_name_plural = 'Plataformas de juego'


class Regalo(models.Model):
    idregalo = models.IntegerField(primary_key=True)
    nombreregalo = models.CharField(max_length=100)
    descripcionregalo = models.CharField(max_length=200, blank=True, null=True)
    valorregalo = models.DecimalField(max_digits=10, decimal_places=2)
    estadoregalo = models.CharField(max_length=20)
    fechaultimaactualizacion = models.DateTimeField()
    urlimagen = models.CharField(max_length=255)

    def __str__(self):
        return self.nombreregalo

    class Meta:
        managed = False
        db_table = 'regalo'
        verbose_name = 'Regalo'
        verbose_name_plural = 'Regalos'
