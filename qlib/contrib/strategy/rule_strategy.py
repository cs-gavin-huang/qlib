import copy
import warnings
import numpy as np
import pandas as pd

from ...utils import sample_feature
from ...strategy.base import RuleStrategy, TradingEnhancement
from ...backtest.order import Order


class TWAPStrategy(RuleStrategy, TradingEnhancement):
    def __init__(
        self, 
        step_bar, 
        start_time, 
        end_time, 
        **kwargs,
    ):
        self.step_bar = step_bar
        self.reset(start_time=start_time, end_time=end_time, **kwargs)
        self.trade_amount = {}
        for order in self.trade_order_list:
            self.trade_amount[(order.stock_id, order.direction)] = order.amount // self.trade_len
    
    def reset(self, start_time=None, end_time=None, trade_order_list=None, **kwargs):
        super(SignalStrategy, self).reset(start_time=start_time, end_time=end_time, **kwargs)
        TradingEnhancement.reset(trade_order_list=trade_order_list)

    def generate_order_list(self, **kwargs):
        super(TopkDropoutStrategy, self).generate_order_list()
        trade_start_time = self.trade_dates[self.trade_index - 1]
        trade_end_time = self.trade_dates[self.trade_index]
        order_list = []
        for order in self.trade_order_list:
            _order = Order(
                stock_id=order.stock_id,
                amount=self.trade_amount[(order.stock_id, order.direction)],
                start_time=trade_start_time,
                end_time=trade_end_time,
                direction=order.direction,  # 1 for buy
                factor=order.factor,
            )
            order_list.append(_order)
        return order_list

class SBBStrategy(RuleStrategy, TradingEnhancement):
    """
        (S)elect the (B)etter one among every two adjacent trading (B)ars to sell or buy.
    """
    TREND_MID = 0
    TREND_SHORT = 1
    TREND_LONG = 2

    def __init__(
        self, 
        step_bar, 
        start_time, 
        end_time, 
        **kwargs,
    ):
        self.step_bar = step_bar
        self.reset(start_time=start_time, end_time=end_time, **kwargs)
        self.trade_amount = {}
        self.trade_delay = {} 
        for order in self.trade_order_list:
            self.trade_amount[(order.stock_id, order.direction)] = order.amount // self.trade_len
            self.trade_trend[(order.stock_id, order.direction)] = TREND_MID

    def reset(self, start_time=None, end_time=None, trade_order_list=None, **kwargs):
        super(SignalStrategy, self).reset(start_time=start_time, end_time=end_time, **kwargs)
        TradingEnhancement.reset(trade_order_list=trade_order_list)

    def _pred_price_trend(self, stock_id, pred_start_time=None, pred_end_time=None):
        raise NotImplementedError("pred_price_trend method is not implemented!")

    def generate_order_list(self, trade_start_time, trade_end_time, **kwargs):
        super(TopkDropoutStrategy, self).generate_order_list()
        if self.trade_index == 1:
            pred_start_time, pred_end_time = None, trade_start_time - pd.Timedelta(seconds=1)
        else:
            pred_start_time, pred_end_time = self.trade_dates[self.trade_index - 2], trade_start_time - pd.Timedelta(seconds=1)
        order_list = []
        for order in self.trade_order_list:
            if self.trade_index % 2 == 1:
                _pred_trend = self._pred_price_trend(order.stock_id)
            else:
                _pred_trend = self.trade_trend[(order.stock_id, order.direction)]
            if _pred_trend == TREND_MID:
                _order = Order(
                    stock_id=order.stock_id,
                    amount=self.trade_amount[(order.stock_id, order.direction)],
                    start_time=trade_start_time,
                    end_time=trade_end_time,
                    direction=order.direction,  # 1 for buy
                    factor=order.factor,
                )
                order_list.append(_order)
            else:
                if self.trade_index % 2 == 1:
                    if _pred_trend == self.TREND_SHORT and order.direction == order.SELL or _pred_trend == self.TREND_LONG and order.direction == order.BUY:
                        _order = Order(
                            stock_id=order.stock_id,
                            amount=2*self.trade_amount[(order.stock_id, order.direction)],
                            start_time=trade_start_time,
                            end_time=trade_end_time,
                            direction=order.direction,  # 1 for buy
                            factor=order.factor,
                        )
                        order_list.append(_order)
                else:
                    if _pred_trend == self.TREND_SHORT and order.direction == order.BUY or _pred_trend == self.TREND_LONG and order.direction == order.SELL:
                        _order = Order(
                            stock_id=order.stock_id,
                            amount=2*self.trade_amount[(order.stock_id, order.direction)],
                            start_time=trade_start_time,
                            end_time=trade_end_time,
                            direction=order.direction,  # 1 for buy
                            factor=order.factor,
                        )       
                        order_list.append(_order)
            if self.trade_index % 2 == 1             
                self.trade_trend[(order.stock_id, order.direction)] = _pred_trend

        return order_list

    
class SBBEMAStrategy(SBBStrategy):
    """
        (S)elect the (B)etter one among every two adjacent trading (B)ars to sell or buy with (EMA).
    """
    def __init__(
        self, 
        step_bar, 
        start_time, 
        end_time, 
        instruments="csi300",
        freq="day",
        **kwargs,
    ):
        self.step_bar = step_bar
        if instruments is None:
            warnings.warn("`instruments` is not set, will load all stocks")
            self.instruments = "all"
        if isinstance(instruments, str):
            self.instruments = D.instruments(instruments, filter_pipe=self.filter_pipe)
        self.freq = freq
        self.reset(start_time=start_time, end_time=end_time)

    def _reset_trade_date(self, start_time=None, end_time=None):
        super(SignalStrategy, self)._reset_trade_date(start_time=start_time, end_time=end_time)
        fields = [("EMA...", "signal")]
        self.signal = D.features(instruments, fields, start_time=self.start_time, end_time=self.end_time, freq=self.freq)

    def _pred_price_trend(self, stock_id, pred_start_time=None, pred_end_time=None):
        _sample_signal = sample_feature(self.signal, stock_id, start_time=pred_start_time, end_time=pred_end_time, fields="signal", method="last")
        if _sample_signal.empty:
            return SBBStrategy.TREND_MID
        elif _sample_signal.iloc[0, 0] > 0:
            return SBBStrategy.TREND_LONG
        else:
            return SBBStrategy.TREND_SHORT