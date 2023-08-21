import pytest
from transacao import validateTransaction
    
def testValidateFieldRequiredFail():

    #Campo obrigatório Valor não foi passado
    json_request = "id: 123, nome: Karina" 

    #Chama função de validação e Valida retorno da função
    assert validateTransaction(json_request) == False


def testValidateFieldRequiredOK():

    #Campo obrigatório Valor foi passado
    json_request = "id: 123, nome: Karina, valor: 10" 

    #Chama função de validação e Valida retorno da função
    assert validateTransaction(json_request) == True