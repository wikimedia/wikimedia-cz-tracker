( function () {
	function signSupervisor() {
		var param = '\n\nSem napište svou poznámku supervizora anebo tento text smažte --' + window.username;
		document.getElementById( 'id_supervisor_notes' ).value += param;
		document.getElementById( 'id_supervisor_notes' ).onclick = function () {};
	}
	document.getElementById( 'id_supervisor_notes' ).onclick = function () {
		signSupervisor();
	};
}() );
