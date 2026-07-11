from django.db import models


class Socio(models.Model):
    idsocio = models.IntegerField(primary_key=True)
    idtiposocio = models.ForeignKey('configuracion.Tiposocio', models.DO_NOTHING, db_column='idtiposocio')
    primernombresocio = models.CharField(max_length=40)
    segundonombresocio = models.CharField(max_length=40, blank=True, null=True)
    primerapellidosocio = models.CharField(max_length=40)
    segundoapellidosocio = models.CharField(max_length=40)
    cisocio = models.CharField(unique=True, max_length=10)
    fechanacimientosocio = models.DateField()
    telefonopersonalsocio = models.CharField(max_length=25, blank=True, null=True)
    telefonotrabajosocio = models.CharField(max_length=25, blank=True, null=True)
    direcciondomiciliosocio = models.CharField(max_length=255)
    direcciontrabajosocio = models.CharField(max_length=255, blank=True, null=True)
    sexosocio = models.CharField(max_length=1, blank=True, null=True)
    estadosocio = models.CharField(max_length=10)

    def __str__(self):
        nombre_completo = ' '.join(
            parte
            for parte in (
                self.primernombresocio,
                self.segundonombresocio,
                self.primerapellidosocio,
                self.segundoapellidosocio,
            )
            if parte
        )
        return nombre_completo or f'Socio {self.idsocio}'

    class Meta:
        managed = False
        db_table = 'socio'
        verbose_name = 'Socio'
        verbose_name_plural = 'Socios'


class SolicitudSocio(models.Model):
    ESTADO_PENDIENTE = 'Pendiente'
    ESTADO_APROBADA = 'Aprobada'
    ESTADO_RECHAZADA = 'Rechazada'
    ESTADO_CHOICES = (
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_APROBADA, 'Aprobada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
    )

    idsolicitud = models.AutoField(
        primary_key=True,
        db_column='idsolicitud',
    )
    idjugador = models.ForeignKey('jugadores.Jugador', models.DO_NOTHING, db_column='idjugador')
    idtiposocio = models.ForeignKey(
        'configuracion.Tiposocio',
        models.DO_NOTHING,
        db_column='idtiposocio',
        blank=True,
        null=True,
    )
    primernombresocio = models.CharField(max_length=40)
    segundonombresocio = models.CharField(max_length=40, blank=True, null=True)
    primerapellidosocio = models.CharField(max_length=40)
    segundoapellidosocio = models.CharField(max_length=40)
    cisocio = models.CharField(max_length=10)
    fechanacimientosocio = models.DateField()
    telefonopersonalsocio = models.CharField(max_length=25, blank=True, null=True)
    telefonotrabajosocio = models.CharField(max_length=25, blank=True, null=True)
    direcciondomiciliosocio = models.CharField(max_length=255)
    direcciontrabajosocio = models.CharField(max_length=255, blank=True, null=True)
    sexosocio = models.CharField(max_length=1, blank=True, null=True)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
    )
    fechasolicitud = models.DateTimeField()
    fecharespuesta = models.DateTimeField(blank=True, null=True)
    idusuarioadminrespuesta = models.ForeignKey(
        'auth.User',
        models.DO_NOTHING,
        db_column='idusuarioadminrespuesta',
        blank=True,
        null=True,
    )
    observacion = models.CharField(max_length=255, blank=True, null=True)
    motivorechazo = models.CharField(max_length=255, blank=True, null=True)
    idsocioresultado = models.ForeignKey(
        'socios.Socio',
        models.DO_NOTHING,
        db_column='idsocioresultado',
        blank=True,
        null=True,
    )

    def __str__(self):
        return f'Solicitud socio {self.idsolicitud}'

    class Meta:
        managed = False
        db_table = 'solicitud_socio'
        verbose_name = 'Solicitud de socio'
        verbose_name_plural = 'Solicitudes de socio'


class Cuentabancaria(models.Model):
    idcuentabancaria = models.IntegerField(primary_key=True)
    idsocio = models.ForeignKey('socios.Socio', models.DO_NOTHING, db_column='idsocio')
    nombrebanco = models.CharField(max_length=100)
    numerocuenta = models.CharField(unique=True, max_length=30)
    tipocuenta = models.CharField(max_length=20)
    esprincipal = models.BooleanField(unique=True, blank=True, null=True)
    fecharegistro = models.DateTimeField(blank=True, null=True)
    estadocuenta = models.CharField(max_length=10)

    def __str__(self):
        return f'{self.nombrebanco} - {self.numerocuenta}'

    class Meta:
        managed = False
        db_table = 'cuentabancaria'
        verbose_name = 'Cuenta bancaria'
        verbose_name_plural = 'Cuentas bancarias'
