from __future__ import annotations

from typing import Self


class Client:
    counter = 0
    _all_clients: dict[int, Self] = {}
    _clients_by_username: dict[str, Self] = {}
    _clients_by_email: dict[str, Self] = {}

    def __init__(
        self,
        username: str,
        password: str,
        email: str,
        first_names: str,
        last_name: str,
        balance: float = 0,
        portfolio: dict[str, float] = None,
    ):
        if username in Client._clients_by_username:
            raise ValueError(f"Username {username} is not available")

        self.client_id = Client.counter
        Client.counter += 1

        self.username = username
        self.password = password
        self.email = email
        self.first_names = first_names
        self.last_name = last_name

        self.balance = balance
        self.portfolio = portfolio if portfolio is not None else {}

        Client._all_clients[self.client_id] = self
        Client._clients_by_username[self.username] = self
        Client._clients_by_email[self.email] = self

    def __str__(self):
        return f"{self.first_names} {self.last_name} ({self.username})"

    @classmethod
    def get_client_by_id(cls, id: int):
        return cls._all_clients.get(id)

    @classmethod
    def get_client_by_username(cls, username: str) -> Self:
        return cls._clients_by_username.get(username)

    @classmethod
    def get_client_by_email(cls, email: str) -> Self:
        return cls._clients_by_email.get(email)

    @classmethod
    def resolve(cls, client_info) -> Self:
        """Resolve a client's id, username, or reference to the client."""
        match client_info:
            case int():
                client = Client.get_client_by_id(client_info)
            case str():
                client = Client.get_client_by_username(client_info)
            case Client():
                client = client_info  # if client is entered, replace with client id
            case _:
                raise TypeError("Client, Client id, or Client username must be entered")

        if client is None:
            raise ValueError("Input client info does not correspond to a valid client")

        return client

    def get_id(self) -> int:
        return self.client_id

    def get_balance(self) -> float:
        return self.balance

    def buy_stock(self, ticker: str, price: float, vol: int):
        # remove money from balance
        if self.balance < vol * price:
            raise ValueError(f"Buyer {self.username} has insufficient funds")
        self.balance -= price * vol

        if vol <= 0:
            raise ValueError("Must buy a positive amount")

        if not ticker in self.portfolio:
            self.portfolio[ticker] = vol
        else:
            self.portfolio[ticker] += vol

    def sell_stock(self, ticker: str, price: float, vol: int):
        # add money to balance
        self.balance += price * vol

        if vol <= 0:
            raise ValueError("Must sell a positive amount")

        if not ticker in self.portfolio:
            raise ValueError(f"Seller {self.username} does not own the stock")
        else:
            if self.portfolio[ticker] < vol:
                raise ValueError(f"Seller {self.username} has insufficient stock")
            self.portfolio[ticker] -= vol
            if self.portfolio[ticker] == 0:  # if stock is no longer held
                del self.portfolio[ticker]  # remove from portfolio

    def add_stock_to_portfolio(self, ticker: str, vol: int):
        """Increase a client's tracked portfolio size from external action and reconcile matches."""
        if vol <= 0:
            raise ValueError("Must add a positive amount")

        if ticker not in self.portfolio:
            self.portfolio[ticker] = vol
        else:
            self.portfolio[ticker] += vol

    def add_funds(self, amount: float):
        """Increase a client's cash balance and reconcile matches across all books."""
        if amount <= 0:
            raise ValueError("Must add a positive amount")

        self.balance += amount

    def display_portfolio(self) -> str:
        res = f"Portfolio of {str(self)}:"
        for ticker in self.portfolio:
            res += f"\n  {ticker}:\t  {self.portfolio[ticker]}"
        return res

    def display_balance(self) -> str:
        return f"Cash balance of {str(self)}:\t  {self.balance}"


ClientInfo = Client | int | str
