from django.db import models


class Jugador(models.Model):
    idjugador = models.IntegerField(primary_key=True)
    idsocio = models.ForeignKey('socios.Socio', models.DO_NOTHING, db_column='idsocio', blank=True, null=True)
    avatarjugador = models.CharField(max_length=255, blank=True, null=True)
    aliasjugador = models.CharField(unique=True, max_length=100, blank=True, null=True)
    correojugador = models.CharField(unique=True, max_length=200, blank=True, null=True)
    fecharegistrojugador = models.DateTimeField()
    saldocreditojugador = models.DecimalField(max_digits=10, decimal_places=2)
    estadocuentajugador = models.CharField(max_length=20)

    def __str__(self):
        return self.aliasjugador or self.correojugador or f'Jugador {self.idjugador}'

    class Meta:
        managed = False
        db_table = 'jugador'
        verbose_name = 'Jugador'
        verbose_name_plural = 'Jugadores'
