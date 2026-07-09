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
    patronganador = models.CharField(
        max_length=20,
        db_column='patronganador',
        choices=(
            ('carton_lleno', 'Cartón lleno'),
            ('linea_horizontal', 'Línea horizontal'),
            ('linea_vertical', 'Línea vertical'),
            ('diagonal', 'Diagonal'),
            ('cuatro_esquinas', 'Cuatro esquinas'),
            ('cruz', 'Cruz'),
            ('x', 'Letra X'),
        ),
        default='carton_lleno',
    )
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
    idbingo = models.ForeignKey(
        'bingos.Bingo',
        models.DO_NOTHING,
        db_column='idbingo',
        related_name='cartones',
    )
    # Referencia histórica/de compatibilidad. Los cartones nuevos usarán las
    # participaciones y dejarán esta columna en NULL.
    idpartida = models.ForeignKey('bingos.Partidabingo', models.DO_NOTHING, db_column='idpartida', blank=True, null=True)
    codigocarton = models.CharField(unique=True, max_length=30)
    matriznumeros = models.TextField()
    # Dato histórico/de compatibilidad. El resultado nuevo vive por ronda en
    # CartonPartidaBingo y esta columna quedará en NULL para cartones nuevos.
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


class CartonPartidaBingo(models.Model):
    ESTADO_PENDIENTE = 'Pendiente'
    ESTADO_EN_JUEGO = 'En juego'
    ESTADO_CERRADO = 'Cerrado'
    ESTADO_GANADOR = 'Ganador'
    ESTADO_ANULADO = 'Anulado'

    ORIGEN_HISTORICA_ORIGINAL = 'Historica original'
    ORIGEN_APLICACION = 'Aplicacion'

    idcartonpartidabingo = models.AutoField(primary_key=True)
    idcarton = models.ForeignKey(
        'bingos.Carton',
        models.DO_NOTHING,
        db_column='idcarton',
        related_name='participaciones',
    )
    idpartida = models.ForeignKey(
        'bingos.Partidabingo',
        models.DO_NOTHING,
        db_column='idpartida',
        related_name='participaciones_carton',
    )
    idbingo = models.ForeignKey(
        'bingos.Bingo',
        models.DO_NOTHING,
        db_column='idbingo',
        related_name='participaciones_carton',
    )
    estado_participacion = models.CharField(max_length=20)
    indicevictoria = models.IntegerField(blank=True, null=True)
    es_asignacion_original = models.BooleanField(default=False)
    origen_asignacion = models.CharField(max_length=24)
    motivoestado = models.CharField(max_length=255, blank=True, null=True)
    fechacreacion = models.DateTimeField()
    fechavalidacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'carton_partida_bingo'
        unique_together = (('idcarton', 'idpartida'),)


class BingoGastoOperativo(models.Model):
    ESTADO_REGISTRADO = 'Registrado'
    ESTADO_ANULADO = 'Anulado'

    ESTADOS = (
        (ESTADO_REGISTRADO, ESTADO_REGISTRADO),
        (ESTADO_ANULADO, ESTADO_ANULADO),
    )

    idbingogastooperativo = models.AutoField(primary_key=True)
    idbingo = models.ForeignKey('bingos.Bingo', models.DO_NOTHING, db_column='idbingo')
    concepto = models.CharField(max_length=150)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fechagasto = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_REGISTRADO)
    observacion = models.CharField(max_length=300, blank=True, null=True)
    idusuarioregistro = models.ForeignKey(
        'auth.User',
        models.DO_NOTHING,
        db_column='idusuarioregistro',
        related_name='bingos_gastos_operativos_registrados',
    )
    fechacreacion = models.DateTimeField()
    idusuarioanulacion = models.ForeignKey(
        'auth.User',
        models.DO_NOTHING,
        db_column='idusuarioanulacion',
        related_name='bingos_gastos_operativos_anulados',
        blank=True,
        null=True,
    )
    fechaanulacion = models.DateTimeField(blank=True, null=True)
    motivoanulacion = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'bingo_gasto_operativo'
        verbose_name = 'Gasto operativo de bingo'
        verbose_name_plural = 'Gastos operativos de bingo'


class BingoPremioMaterialCosto(models.Model):
    ESTADO_REGISTRADO = 'Registrado'
    ESTADO_ANULADO = 'Anulado'

    ESTADOS = (
        (ESTADO_REGISTRADO, ESTADO_REGISTRADO),
        (ESTADO_ANULADO, ESTADO_ANULADO),
    )

    idbingopremiomaterialcosto = models.AutoField(primary_key=True)
    idbingo = models.ForeignKey('bingos.Bingo', models.DO_NOTHING, db_column='idbingo')
    # La tabla física valida (idpartidabingo, idbingo) con una FK compuesta.
    idpartidabingo = models.IntegerField(db_column='idpartidabingo')
    descripcionpremio = models.CharField(max_length=150)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_REGISTRADO)
    observacion = models.CharField(max_length=300, blank=True, null=True)
    idusuarioregistro = models.ForeignKey(
        'auth.User',
        models.DO_NOTHING,
        db_column='idusuarioregistro',
        related_name='bingos_costos_premios_materiales_registrados',
    )
    fechacreacion = models.DateTimeField()
    idusuarioanulacion = models.ForeignKey(
        'auth.User',
        models.DO_NOTHING,
        db_column='idusuarioanulacion',
        related_name='bingos_costos_premios_materiales_anulados',
        blank=True,
        null=True,
    )
    fechaanulacion = models.DateTimeField(blank=True, null=True)
    motivoanulacion = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'bingo_premio_material_costo'
        verbose_name = 'Costo de premio material de bingo'
        verbose_name_plural = 'Costos de premios materiales de bingo'


class BingoCierreFinanciero(models.Model):
    ESTADO_ABIERTO = 'Abierto'
    ESTADO_CERRADO = 'Cerrado'

    ESTADOS = (
        (ESTADO_ABIERTO, ESTADO_ABIERTO),
        (ESTADO_CERRADO, ESTADO_CERRADO),
    )

    idbingocierrefinanciero = models.AutoField(primary_key=True)
    idbingo = models.OneToOneField(
        'bingos.Bingo',
        models.DO_NOTHING,
        db_column='idbingo',
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_ABIERTO)
    cartonesvendidosunicos = models.IntegerField()
    recaudacionregistrada = models.DecimalField(max_digits=12, decimal_places=2)
    premiosefectivofinalizados = models.DecimalField(max_digits=12, decimal_places=2)
    costospremiosmateriales = models.DecimalField(max_digits=12, decimal_places=2)
    gastosoperativos = models.DecimalField(max_digits=12, decimal_places=2)
    resultadoprovisional = models.DecimalField(max_digits=12, decimal_places=2)
    utilidadbruta = models.DecimalField(max_digits=12, decimal_places=2)
    utilidadneta = models.DecimalField(max_digits=12, decimal_places=2)
    totalrondas = models.IntegerField()
    rondasfinalizadas = models.IntegerField()
    rondascanceladas = models.IntegerField()
    rondaspendientes = models.IntegerField()
    fechacalculo = models.DateTimeField()
    fechacierre = models.DateTimeField(blank=True, null=True)
    idusuariocierre = models.ForeignKey(
        'auth.User',
        models.DO_NOTHING,
        db_column='idusuariocierre',
        related_name='bingos_cierres_financieros',
        blank=True,
        null=True,
    )
    observacioncierre = models.CharField(max_length=500, blank=True, null=True)
    fechacreacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'bingo_cierre_financiero'
        verbose_name = 'Cierre financiero de bingo'
        verbose_name_plural = 'Cierres financieros de bingo'


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
