from django.db import models


class Bingo(models.Model):
    idbingo = models.IntegerField(primary_key=True)
    titulobingo = models.CharField(max_length=150)
    fechaprogramadabingo = models.DateTimeField()
    tipobingo = models.CharField(max_length=20)
    lugarbingo = models.CharField(max_length=255, blank=True, null=True)
    urlsesionbingo = models.CharField(max_length=255, blank=True, null=True)
    preciocarton = models.DecimalField(max_digits=10, decimal_places=2)
    premiomayor = models.DecimalField(max_digits=10, decimal_places=2)
    descripcionpremiomayor = models.CharField(max_length=100)
    estadobingo = models.CharField(max_length=20)
    rutaimagenpremiomayor = models.CharField(max_length=300, blank=True, null=True)
    urlvideopromocional = models.CharField(max_length=300, blank=True, null=True)
    descripcionpremios = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return self.titulobingo

    class Meta:
        managed = False
        db_table = 'bingo'
        verbose_name = 'Bingo'
        verbose_name_plural = 'Bingos'


class Partidabingo(models.Model):
    idpartidabingo = models.IntegerField(primary_key=True)
    idbingo = models.ForeignKey('bingos.Bingo', models.DO_NOTHING, db_column='idbingo')
    idjugadorganador = models.ForeignKey('jugadores.Jugador', models.DO_NOTHING, db_column='idjugadorganador', blank=True, null=True)
    nombreronda = models.CharField(max_length=100)
    valorefectivo = models.DecimalField(max_digits=10, decimal_places=2)
    premiomaterial = models.CharField(max_length=150)
    estadopartida = models.CharField(max_length=20)
    bolascantadas = models.TextField()
    ultimabola = models.IntegerField()
    haydesempate = models.BooleanField(blank=True, null=True)
    idbingadores = models.TextField(blank=True, null=True)
    bolamayordesempate = models.IntegerField(blank=True, null=True)
    horainicio = models.DateTimeField()
    horafin = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.nombreronda

    class Meta:
        managed = False
        db_table = 'partidabingo'
        verbose_name = 'Partida de bingo'
        verbose_name_plural = 'Partidas de bingo'


class Carton(models.Model):
    idcarton = models.IntegerField(primary_key=True)
    idjugador = models.ForeignKey('jugadores.Jugador', models.DO_NOTHING, db_column='idjugador', blank=True, null=True)
    idpartida = models.ForeignKey('bingos.Partidabingo', models.DO_NOTHING, db_column='idpartida', blank=True, null=True)
    codigocarton = models.CharField(unique=True, max_length=30)
    matriznumeros = models.TextField()
    indicevictoria = models.IntegerField(blank=True, null=True)
    preciopagado = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fechacompra = models.DateTimeField(blank=True, null=True)
    estadocarton = models.CharField(max_length=20)

    def __str__(self):
        return self.codigocarton

    class Meta:
        managed = False
        db_table = 'carton'
        verbose_name = 'Carton'
        verbose_name_plural = 'Cartones'


class Sesionjuego(models.Model):
    idsesion = models.IntegerField(primary_key=True)
    idplataforma = models.ForeignKey('configuracion.Plataformajuego', models.DO_NOTHING, db_column='idplataforma')
    idjugador = models.ForeignKey('jugadores.Jugador', models.DO_NOTHING, db_column='idjugador')
    idpartida = models.ForeignKey('bingos.Partidabingo', models.DO_NOTHING, db_column='idpartida')
    fechainiciosesion = models.DateTimeField()
    fechafinsesion = models.DateTimeField(blank=True, null=True)
    ipconexion = models.CharField(max_length=50, blank=True, null=True)
    dispositivoconexion = models.CharField(max_length=50, blank=True, null=True)
    estadosesion = models.CharField(max_length=15)
    latenciaping = models.IntegerField(blank=True, null=True)
    navegadorweb = models.CharField(max_length=150, blank=True, null=True)
    tokenconexion = models.CharField(unique=True, max_length=255)
    motivocierre = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f'Sesion {self.idsesion}'

    class Meta:
        managed = False
        db_table = 'sesionjuego'
        verbose_name = 'Sesion de juego'
        verbose_name_plural = 'Sesiones de juego'
