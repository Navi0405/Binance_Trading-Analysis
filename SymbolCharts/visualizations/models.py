from django.db import models

class account(models.Model):
    symbol = models.CharField(max_length=50)
    orderId = models.BigIntegerField()
    side = models.CharField(max_length=10)
    price = models.TextField()
    qty = models.TextField()
    realizedPnl = models.TextField()
    marginAsset = models.TextField()
    quoteQty = models.TextField()
    commission = models.TextField()
    commissionAsset = models.TextField()
    time = models.DateTimeField()
    positionSide = models.TextField()
    buyer = models.BooleanField()
    maker = models.BooleanField()
    
    class Meta:
        db_table = 'account'
