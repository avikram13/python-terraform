import subprocess
import os
import json
import logging

from python_terraform.tfstate import Tfstate

log = logging.getLogger(__name__)


class Terraform:
    """
    Wrapper of terraform command line tool
    https://www.terraform.io/
    """

    def __init__(self, working_dir=None,
                 targets=None,
                 state=None,
                 variables=None,
                 parallelism=None,
                 var_file=None,
                 terraform_bin_path=None):
        self.working_dir = working_dir
        self.state = state
        self.targets = [] if targets is None else targets
        self.variables = dict() if variables is None else variables
        self.parallelism = parallelism
        self.terraform_bin_path = terraform_bin_path \
            if terraform_bin_path else 'terraform'
        self.var_file = var_file
        self.input = False

        # store the tfstate data
        self.tfstate = dict()

    def apply(self,
              working_dir=None,
              no_color=True,
              **kwargs):
        """
        refer to https://terraform.io/docs/commands/apply.html
        :param working_dir: working folder
        :param no_color: Disables output with coloring.
        :returns return_code, stdout, stderr
        """
        if not working_dir:
            working_dir = self.working_dir

        option_dict = dict()
        option_dict['state'] = self.state
        option_dict['target'] = self.targets
        option_dict['var'] = self.variables
        option_dict['var_file'] = self.var_file
        option_dict['parallelism'] = self.parallelism
        if no_color:
            option_dict['no_color'] = ''
        option_dict['input'] = self.input

        option_dict.update(kwargs)

        args = [working_dir] if working_dir else []

        ret, out, err = self.cmd('apply', *args, **option_dict)

        if ret != 0:
            raise RuntimeError(err)

    def generate_cmd_string(self, cmd, *args, **kwargs):
        """
        for any generate_cmd_string doesn't written as public method of terraform

        examples:
        1. call import command,
        ref to https://www.terraform.io/docs/commands/import.html
        --> generate_cmd_string call:
                terraform import -input=true aws_instance.foo i-abcd1234
        --> python call:
                tf.generate_cmd_string('import', 'aws_instance.foo', 'i-abcd1234', input=True)

        2. call apply command,
        --> generate_cmd_string call:
                terraform apply -var='a=b' -var='c=d' -no-color the_folder
        --> python call:
                tf.generate_cmd_string('apply', the_folder, no_color='', var={'a':'b', 'c':'d'})

        :param cmd: command and sub-command of terraform, seperated with space
                    refer to https://www.terraform.io/docs/commands/index.html
        :param args: argument other than options of a command
        :param kwargs: same as kwags in method 'cmd'
        :return: string of valid terraform command
        """
        cmds = cmd.split()
        cmds = [self.terraform_bin_path] + cmds

        for k, v in kwargs.items():
            if '_' in k:
                k = k.replace('_', '-')

            if type(v) is list:
                for sub_v in v:
                    cmds += ['-{k}={v}'.format(k=k, v=sub_v)]
                continue

            if type(v) is dict:
                for sub_k, sub_v in v.items():
                    cmds += ["-{k}='{var_k}={var_v}'".format(k=k,
                                                             var_k=sub_k,
                                                             var_v=sub_v)]
                continue

            # simple flag,
            if v == '':
                cmds += ['-{k}'.format(k=k)]
                continue

            if not v:
                continue

            if type(v) is bool:
                v = 'true' if v else 'false'

            cmds += ['-{k}={v}'.format(k=k, v=v)]

        cmds += args
        cmd = ' '.join(cmds)
        return cmd

    def cmd(self, cmd, *args, **kwargs):
        """
        run a terraform command, if success, will try to read state file
        :param cmd: command and sub-command of terraform, seperated with space
                    refer to https://www.terraform.io/docs/commands/index.html
        :param args: argument other than options of a command
        :param kwargs:  any option flag with key value other than variables,
                if there's a dash in the option name, use under line instead of dash, ex -no-color --> no_color
                if it's a simple flag with no value, value should be empty string
                if it's a boolean value flag, assign True or false
                if it's a flag could be used multiple times, assign list to it's value
                if it's a "var" variable flag, assign dictionary to it
                if a value is None, will skip this option
        :return: ret_code, out, err
        """
        cmd_string = self.generate_cmd_string(cmd, *args, **kwargs)
        log.debug('command: {c}'.format(c=cmd_string))

        p = subprocess.Popen(cmd_string, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=True)
        out, err = p.communicate()
        ret_code = p.returncode
        log.debug('output: {o}'.format(o=out))

        if ret_code == 0:
            self.read_state_file()
        else:
            log.warn('error: {e}'.format(e=err))
        return ret_code, out.decode('utf-8'), err.decode('utf-8')

    def output(self, name):
        """
        https://www.terraform.io/docs/commands/output.html
        :param name: name of output
        :return: output value
        """
        ret, out, err = self.cmd('output', name, json='')

        if ret != 0:
            return None
        out = out.lstrip()

        output_dict = json.loads(out)
        return output_dict['value']

    def read_state_file(self, file_path=None):
        """
        read .tfstate file
        :param file_path: relative path to working dir
        :return: states file in dict type
        """

        if not file_path:
            file_path = self.state

        if not file_path:
            file_path = 'terraform.tfstate'

        if self.working_dir:
            file_path = os.path.join(self.working_dir, file_path)

        self.tfstate = Tfstate.load_file(file_path)
