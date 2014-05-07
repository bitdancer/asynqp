import asyncio
import asynqp
from asyncio import test_utils
from asynqp import spec
from asynqp import protocol
from asynqp.connection import ConnectionInfo, open_connection
from unittest import mock


class LoopContext:
    def given_an_event_loop(self):
        self.loop = asyncio.get_event_loop()

    def go(self):
        test_utils.run_briefly(self.loop)


class MockLoopContext(LoopContext):
    def given_an_event_loop(self):
        self.loop = mock.Mock(spec=asyncio.AbstractEventLoop)


class ConnectionContext(LoopContext):
    def given_the_pieces_i_need_for_a_connection(self):
        self.protocol = mock.Mock(spec=protocol.AMQP)
        self.protocol.transport = mock.Mock()
        self.protocol.send_frame._is_coroutine = False  # :(

        self.dispatcher = protocol.Dispatcher(self.loop)
        self.connection_info = ConnectionInfo('guest', 'guest', '/')


class OpenConnectionContext(ConnectionContext):
    def given_an_open_connection(self):
        task = asyncio.async(open_connection(self.loop, self.protocol, self.dispatcher, self.connection_info))
        self.go()

        start_frame = asynqp.frames.MethodFrame(0, spec.ConnectionStart(0, 9, {}, 'PLAIN AMQPLAIN', 'en_US'))
        self.dispatcher.dispatch(start_frame)
        self.go()

        self.frame_max = 131072
        tune_frame = asynqp.frames.MethodFrame(0, spec.ConnectionTune(0, self.frame_max, 600))
        self.dispatcher.dispatch(tune_frame)
        self.go()

        open_ok_frame = asynqp.frames.MethodFrame(0, spec.ConnectionOpenOK(''))
        self.dispatcher.dispatch(open_ok_frame)
        self.protocol.reset_mock()
        self.go()

        self.connection = task.result()


class ProtocolContext(LoopContext):
    def given_a_connected_protocol(self):
        self.transport = mock.Mock(spec=asyncio.Transport)
        self.dispatcher = protocol.Dispatcher(self.loop)
        self.protocol = protocol.AMQP(self.dispatcher, self.loop)
        self.protocol.connection_made(self.transport)


class OpenChannelContext(OpenConnectionContext):
    def given_an_open_channel(self):
        self.channel = self.open_channel()
        self.protocol.reset_mock()

    def open_channel(self, channel_id=1):
        task = asyncio.async(self.connection.open_channel(), loop=self.loop)
        self.go()
        open_ok_frame = asynqp.frames.MethodFrame(channel_id, spec.ChannelOpenOK(''))
        self.dispatcher.dispatch(open_ok_frame)
        self.go()
        return task.result()


class QueueContext(OpenChannelContext):
    def given_a_queue(self):
        queue_name = 'my.nice.queue'
        task = asyncio.async(self.channel.declare_queue(queue_name, durable=True, exclusive=True, auto_delete=True), loop=self.loop)
        self.go()
        frame = asynqp.frames.MethodFrame(self.channel.id, spec.QueueDeclareOK(queue_name, 123, 456))
        self.dispatcher.dispatch(frame)
        self.go()
        self.queue = task.result()

        self.protocol.reset_mock()


class ExchangeContext(OpenChannelContext):
    def given_an_exchange(self):
        task = asyncio.async(self.channel.declare_exchange('my.nice.exchange', 'fanout', durable=True, auto_delete=False, internal=False),
                             loop=self.loop)
        self.go()
        frame = asynqp.frames.MethodFrame(self.channel.id, spec.ExchangeDeclareOK())
        self.dispatcher.dispatch(frame)
        self.go()
        self.exchange = task.result()

        self.protocol.reset_mock()
